import math
import os
import ctypes
from ctypes import *
import numpy as np
from nplab.instrument import Instrument
from nplab.instrument.electronics import adlink9812_constants
from nplab.utils.gui import *
from nplab.ui.ui_tools import *
from nplab.experiment.dynamic_light_scattering import dls_signal_postprocessing 
import nplab
import datetime
import matplotlib 
import matplotlib.pyplot as plt 
### Steps of PCI-DASK applications:
#
# Full documentation: ADLINK PCIS-DASK User's Manual
# Function reference: http://www.adlinktech.com/publications/manual/Software/PCIS-DASK-X/PSDASKFR.pdf

#	1. Register card
#	2. Configuration function
#	3. AI/AO/DI/DO Operation function
#		AI: analog input
#			non-buffered single-point AI: poll device for data
#			buffered: interrupt transfer/DMA (direct memory access) to transfer data from device to user buffer
#		AO: analog output
#		DI: digital input
#		DO: digital output
#		3.1 ---- Configuration ---
#			Must configure your card (our case: AI_9812_Config, passing card_id (from registration and parameters for registering))
#	4. Release card


DATATYPE = c_ushort
VERSION = 0.01


class Adlink9812(Instrument):

	def __init__(self, dll_path="C:\ADLINK\PCIS-DASK\Lib\PCI-Dask64.dll",verbose=False,debug=False):
		"""Initialize DLL and configure card"""
		# super(Adlink9812,self).__init__()
		self.debug = debug
		if not os.path.exists(dll_path):
			if self.debug != True:
				raise ValueError("Adlink DLL not found: {}".format(dll_path))
		else:
			self.dll = CDLL(dll_path)
			self.card_id = self.register_card()
			self.configure_card()

	def __del__(self):
		'''Deregister the card on object deletion'''
		self.release_card()


	def register_card(self,channel = 0):
		outp = ctypes.c_int16(self.dll.Register_Card(adlink9812_constants.PCI_9812,c_ushort(channel)))
		if outp.value < 0:
			print "Register_Card: nonpositive value -> error code:", outp
		return outp.value

	def release_card(self):
		releaseErr = ctypes.c_int16(self.dll.Release_Card(self.card_id))
		if releaseErr.value != 0:
			print "Release_Card: Non-zero status code:", releaseErr.value
		return

	def get_card_sample_rate(self,sampling_freq):
		actual = c_double()
		statusCode = ctypes.c_int16(DLL.GetActualRate(self.card_id,c_double(sampling_freq), byref(actual)))

		if statusCode.value != 0:
			print "GetActualRate: Non-zero status code:", statusCode.value
		return actual.value

	def get_qt_ui(self):
		return Adlink9812UI(card=self,debug = self.debug)

	@staticmethod
	def get_qt_ui_cls():
		return Adlink9812UI

	def configure_card(self):
		#Configure card for recording
		configErr = ctypes.c_int16(self.dll.AI_9812_Config(
			c_ushort(self.card_id),
			c_ushort(adlink9812_constants.P9812_TRGMOD_SOFT), #Software trigger mode
			c_ushort(adlink9812_constants.P9812_TRGSRC_CH0),  #Channel 0 
			c_ushort(adlink9812_constants.P9812_TRGSLP_POS),  #Positive edge trigger
			c_ushort(adlink9812_constants.P9812_CLKSRC_INT),  #Internal clock
			c_ushort(0x80), 								  #Trigger threshold = 0.00V
			c_ushort(0),										#Postcount - setting for Middle/Delay Trigger
			))

		if configErr.value != 0:
			print "AI_9812_Config: Non-zero status code:", configErr.value
		return


	def convert_to_volts(self,inputBuffer, outputBuffer, buffer_size):
		convertErr = ctypes.c_int16(self.dll.AI_ContVScale(
				c_ushort(self.card_id),							#CardNumber
				c_ushort(adlink9812_constants.AD_B_1_V),		#AdRange
				inputBuffer, 									#DataBuffer   - array storing raw 16bit A/D values
				outputBuffer, 									#VoltageArray - reference to array storing voltages
				c_uint32(buffer_size) 							#Sample count - number of samples to be converted
			))

		if convertErr.value != 0:
			print "AI_ContVScale: Non-zero status code:", convertErr.value
		return 


	def synchronous_analog_input_read(self,sample_freq, sample_count,verbose = False,channel=0):
		#Initialize Buffers
		#databuffer for holding A/D samples + metadata bits
		dataBuff = (c_ushort*sample_count)()
		#voltageArray for holding converted voltage values
		voltageOut = (c_double*sample_count)()

		#Sample data, Mode: Synchronous
		readErr = ctypes.c_int16(self.dll.AI_ContReadChannel(
			c_ushort(self.card_id), 								#CardNumber
			c_ushort(channel),       						#Channel
			c_ushort(adlink9812_constants.AD_B_1_V),		#AdRange
			dataBuff,												#Buffer
			c_uint32(sample_count),							#ReadCount
			c_double(sample_freq),							#SampleRate (Hz)
			c_ushort(adlink9812_constants.SYNCH_OP)			#SyncMode
		))

		if readErr.value != 0:
			print "AI_ContReadChannel: Non-zero status code:", readErr.value

		#Convert to volts
		self.convert_to_volts(dataBuff,voltageOut,sample_count)
		return np.asarray(voltageOut)

	def asynchronous_double_buffered_analog_input_read(self,sample_freq,sample_count,card_buffer_size = 500000,verbose=False, channel = 0):
		'''
		Non-Triggered Double-Buffered Asynchronous  Analog Input Continuous Read
		Steps: [Adlink PCIS-DASK manual,page 47]

		1. AI_XXXX_Config
			Configure the card for the asynchronous mode

		2. AI_AsyncDblBufferMode 
			Enable double buffered mode

		3. AI_ContReadChannel
			Read from a single channel (=0)

		4. while not stop:

			4.1 if (AI_AsyncDblBufferHaldReady):   #Check if buffer is half full]
				
				4.1.1 AI_AsyncDblBufferTransfer	   #Transfer data from card buffer into user buffer
			
		5. AI_AsyncClear
		6. Convert all data to volts and return

		'''
		
		#AI_AsyncDblBufferMode - initialize Double Buffer Mode
		buffModeErr = ctypes.c_int16(self.dll.AI_AsyncDblBufferMode(c_ushort(self.card_id),ctypes.c_bool(1)))
		if verbose or buffModeErr.value != 0:
			print "AI_AsyncDblBufferMode: Non-zero status code",buffModeErr.value

		#card buffer
		cardBuffer = (c_ushort*card_buffer_size)()

		#user buffers
		user_buffer_size = card_buffer_size/2 #half due to being full when buffer is read
		nbuff = int(math.ceil(sample_count/float(user_buffer_size)))
		
		# uBs = [(c_double*user_buffer_size)()]*nbuff
		uBs = []
		print uBs
		# oBs = [(c_double*user_buffer_size)()]*nbuff
		oBs = []
		if verbose:
			print "Number of user buffers:", nbuff

		#AI_ContReadChanne

		readErr = ctypes.c_int16(self.dll.AI_ContReadChannel(
			c_ushort(self.card_id), 					#CardNumber
			c_ushort(channel),       			#Channel
			c_ushort(adlink9812_constants.AD_B_1_V),		#AdRange
			cardBuffer,									#Buffer
			c_uint32(card_buffer_size),			#ReadCount
			c_double(sample_freq),				#SampleRate (Hz)
			c_ushort(adlink9812_constants.ASYNCH_OP)		#SyncMode - Asynchronous
		))

		if verbose or readErr.value != 0:
			print "AI_ContReadChannel: Non-zero status code",readErr.value

		#AI_AsyncDblBufferHalfReader
		#I16 AI_AsyncDblBufferHalfReady (U16 CardNumber, BOOLEAN *HalfReady,BOOLEAN *StopFlag)
		
		for i in range(nbuff):
			currentBuffer = (c_double*user_buffer_size)()
			halfReady = c_bool(0)
			stopFlag = c_bool(0)
			while halfReady.value != True:
				buffReadyErr = ctypes.c_int16(self.dll.AI_AsyncDblBufferHalfReady(
					c_ushort(self.card_id),
					ctypes.byref(halfReady),
					ctypes.byref(stopFlag))
				)
				if buffReadyErr.value!=0:
					print "buffReadErr:",buffReadyErr.value
					print "HalfReady:",halfReady.value
		
			#AI_AsyncDblBufferTransfer
			#I16 AI_AsyncDblBufferTransfer (U16 CardNumber, U16 *Buffer)
			buffTransferErr = ctypes.c_int16(self.dll.AI_AsyncDblBufferTransfer(c_ushort(self.card_id), ctypes.byref(currentBuffer)))
			uBs.append(currentBuffer)
			if buffTransferErr.value != 0:
				print "buffTransferErr:",buffTransferErr.value

		accessCnt = ctypes.c_int32(0)
		clearErr = ctypes.c_int16(self.dll.AI_AsyncClear(self.card_id, ctypes.byref(accessCnt)))
		if verbose:
			print "AI_AsyncClear,AccessCnt:", accessCnt.value
		
		#concatenate user buffer onto existing numpy array
		#reinitialize user buffer

		for i in range(nbuff):
			oB = (c_double*user_buffer_size)()
			convertErr = ctypes.c_int16(self.dll.AI_ContVScale(
			c_ushort(self.card_id),				#CardNumber
			c_ushort(adlink9812_constants.AD_B_1_V),	#AdRange
			uBs[i], 					#DataBuffer   - array storing raw 16bit A/D values
			oB, 					#VoltageArray - reference to array storing voltages
			c_uint32(user_buffer_size) 			#Sample count - number of samples to be converted
			))
			oBs.append(oB)
			if convertErr.value != 0:
				print "AI_ContVScale: Non-zero status code:", convertErr.value
		return np.concatenate(oBs)

	@staticmethod
	def get_times(dt,nsamples):
		return [i*dt for i in range(nsamples)]

	def capture(self,sample_freq, sample_count,verbose = False):
		assert(sample_freq <= int(2e7) and sample_freq > 1)
		dt = 1.0/sample_freq
		if self.debug:
			print "---DEBUG MODE ENABLED---"
			debug_out = (2.0*np.random.rand(sample_count))-1.0 
			return debug_out,dt

		elif sample_count > 100000:
			return self.asynchronous_double_buffered_analog_input_read(sample_freq= sample_freq,sample_count = sample_count,verbose = verbose),dt
		else:
			return self.synchronous_analog_input_read(sample_freq= sample_freq,sample_count = sample_count,verbose = verbose),dt





class Adlink9812UI(QtWidgets.QWidget, UiTools):
	def __init__(self,card, parent=None,debug = False, verbose = False):
		if not isinstance(card, Adlink9812):
			raise ValueError("Object is not an instnace of the Adlink9812 Daq")
		super(Adlink9812UI, self).__init__()
		self.card = card 
		self.parent = parent
		self.debug = debug
		self.verbose = verbose

		#TODO - add adlink9812.ui file properly
		uic.loadUi(os.path.join(os.path.dirname(__file__), 'adlink9812.ui'), self)

		#daq_settings_layout
		self.sample_freq_textbox.textChanged.connect(self.set_sample_freq)
		self.sample_count_textbox.textChanged.connect(self.set_sample_count)
		self.series_name_textbox.textChanged.connect(self.set_series_name)
		
		#processing_stages_layout
		self.threshold_textbox.textChanged.connect(self.set_threshold)
		self.binning_textbox.textChanged.connect(self.set_bin_width)

		#actions_layout
		self.capture_button.clicked.connect(self.capture)

		self.set_sample_freq()
		self.set_sample_count()
		self.set_series_name()
		self.set_bin_width()
		self.set_threshold()
	
	def set_threshold(self):
		try:
			self.difference_threshold = float(self.threshold_textbox.text())
		except Exception, e:
			print "Failed parsing difference_threshold: {0}".format(self.threshold_textbox.text())
		return

	def set_bin_width(self):
		try:
			self.bin_width = float(self.binning_textbox.text())
		except Exception, e:
			print "Failed parsing difference_threshold: {0}".format(self.binning_textbox.text())
		return

	def set_sample_freq(self):
		MHz = 1e6
		try:
			self.sample_freq = int(float(self.sample_freq_textbox.text())*MHz)
		except Exception,e:
			print "Failed parsing sampling frequency to float:",self.sample_freq_textbox.text()
			return
		return

	def set_sample_count(self):
		try:


			self.sample_count = int(float(self.sample_count_textbox.text()))
			if self.verbose>0:
				print "Sample Count: {0} [Counts]".format(self.sample_count)

			self.sample_count = int(float(self.sample_count_textbox.text()))

		except Exception,e:
			print "Failed parsing sample count to int:",self.sample_freq_textbox.text()
		return

	def set_series_name(self):
		self.series_group = self.series_name_textbox.text()
		return

	def plot_series(self,voltages, dt, timestamp):
		
		times = self.card.get_times(dt, len(voltages))
		fig, [ax1,ax2] = plt.subplots(2)
		
		threshold = 0.4

		photon_count = dls_signal_postprocessing.count_photons(voltages,count_threshold=threshold)
		ax1.plot(times, voltages)
		ax1.set_xlabel("Time [s]")
		ax1.set_ylabel("Voltage [V]")
		ax1.set_title("Adlink9812 Capture, Timestamp: {0}, Photons: {1}".format(timestamp,photon_count))
		
		d_voltages = dls_signal_postprocessing.signal_diff(voltages)

		vmin = np.min(voltages)
		vmax = np.max(voltages)
		vspan = abs(vmax-vmin)

		voltages, dt = self.card.capture(sample_freq=self.sample_freq, sample_count=self.sample_count)

		ax2.plot(times[0:len(d_voltages)],abs(d_voltages))
		ax2.plot(times[0:len(d_voltages)],[threshold*vspan]*len(d_voltages),'r',label="count threshold")
		ax2.set_xlabel("Time [s]")
		ax2.set_ylabel("|$\Delta$Voltage| [V]")
		ax2.legend()
		ax2.set_title("Difference voltage plot".format(timestamp,photon_count))

		plt.tight_layout()
		plt.show()
		return


	def postprocess_raw(self,voltages,dt,save,plot,group,axes):

		vmean = np.mean(voltages)
		vmax = np.max(voltages)
		vmin = np.min(voltages)
		vstd = np.std(voltages)
		vpp = np.abs(vmax-vmin)

		print "---Raw---"
		attrs = {
			
			"device": "adlink9812",
			"type": "raw_voltage",
			"_units": "volts",
			"sample_count": self.sample_count,
			"sampling_frequency":self.sample_freq,
			"dt": dt,
			"sampling_time_interval":dt*self.sample_count,
			"vmean":vmean,
			"vstdev": vstd,
			"vmax":vmax,
			"vmin":vmin,
			"vpp":vpp,
			"X label": "Sample Index",
			"Y label": "Voltage [V]"
			}

		if save and self.raw_checkbox.isChecked():
			print "Saving: Raw"
			group.create_dataset("raw_voltage",data=voltages, attrs = attrs)
			group.file.flush()

		if plot and self.raw_checkbox.isChecked():
			print "Plotting: Raw"
			times = dt*np.arange(0,self.sample_count)
			axes[-1].plot(times,voltages,'x')
			axes[-1].set_xlabel("Time [s]")
			axes[-1].set_ylabel("Voltage [V]")
		print "---/Raw---"
		return 

	def postprocess_difference(self,voltages,dt,save,plot,group,axes):
		#record/plot raw
		self.postprocess_raw(voltages=voltages,dt=dt,save=save,plot=plot,group=group,axes=axes[0:-1])
		
		#compute rounded difference
		rounded_diff = dls_signal_postprocessing.signal_diff(voltages)
		#metaparameters
		total_counts = np.sum(np.absolute(rounded_diff))
		sample_time_interval = dt*self.sample_count
		count_frequency = total_counts/float(sample_time_interval)

		print "---Difference---"

		attrs = attrs = {
			
			"device": "adlink9812",
			"type": "difference",
			"_units": "none",
			"total_counts" : total_counts,
			"sampling_time_interval":dt*self.sample_count,
			"count_frequency" : count_frequency,
			"X label": "Sample Index",
			"Y label": "Normalized Voltage Difference [V]"
			}
		if save and self.difference_checkbox.isChecked():
			print "Saving Difference stage"
			group.create_dataset("diff_voltage",data=rounded_diff, attrs = attrs)
			group.file.flush()

		if plot and self.difference_checkbox.isChecked():
			print "Plotting Difference stage"
			times = dt*np.arange(0,self.sample_count-1)
			axes[-1].plot(times,rounded_diff,'x')
			axes[-1].set_xlabel("Time [s] (interval lower bound)")
			axes[-1].set_ylabel("Voltage difference [V]")

		print "Total Counts:", total_counts
		print "Sampling Time Interval:", sample_time_interval
		print "Count freuquency:", count_frequency

		print "---/Difference---"

		return rounded_diff

	#####THRESHOLDING DEACTIVATED######
	# def postprocess_threshold(self,voltages, dt, save, group):
	# 	print "Thresholding step deactivated"
	# 	thresholded = dls_signal_postprocessing.threshold(voltages=voltages)
	# 	attrs = attrs = {
			
	# 		"device": "adlink9812",
	# 		"type": "thresholded",
	# 		"_units": "int",
	# 		"sample_count": self.sample_count,
	# 		"frequency":self.sample_freq,
	# 		"dt": dt,
	# 		"X label": "Sample Index",
	# 		"Y label": "Thresholded pulses [Int]"
	# 		}
	# 	if save and self.threshold_checkbox.isChecked():
	# 		print "Saving Threshold stage"
	# 		group.create_dataset("thresholded_pulses",data=thresholded, attrs = attrs)
	# 		group.file.flush()	

		
	# 	return thresholded

	def post_process_binning(self,voltages,dt,save,plot,group,axes):
		rounded_diff = self.postprocess_difference(voltages=voltages,dt=dt,save=save,plot=plot,group=group,axes=axes[0:-1])
		
		time_bin_width = self.bin_width
		index_bin_width = int(math.ceil((float(time_bin_width)/float(dt))))

		binned_counts = dls_signal_postprocessing.binning(thresholded=np.absolute(rounded_diff).astype(int),index_bin_width=index_bin_width)
		time_bins = time_bin_width*np.arange(0,len(binned_counts))

		binned_total_counts = np.sum(np.absolute(binned_counts))
		binned_sample_time_interval = time_bins[-1]
		binned_count_frequency = binned_total_counts/float(binned_sample_time_interval)

		print "---Binning---"

		attrs = attrs = {
			
			"device": "adlink9812",
			"type": "binned_counts",
			"_units": "count",
			"time_bin_width":time_bin_width,
			"index_bin_width":index_bin_width,
			"binned_total_counts" : binned_total_counts ,
			"binned_sample_time_interval": binned_sample_time_interval,
			"binned_count_frequency": binned_count_frequency,
			"X label": "Time [s] (time bins lower bound)",
			"Y label": "Photon Count"
			}

		if save and self.binning_checkbox.isChecked():
			print "Saving: Binning"
			group.create_dataset("photon_count",data=[time_bins,binned_counts], attrs = attrs)
			group.file.flush()

		if plot and self.binning_checkbox.isChecked():
			print "Plotting@ Binning"
			axes[-1].plot(time_bins,binned_counts,'x-')
			axes[-1].set_xlabel("Time [s] (time bin lower bound)")
			axes[-1].set_ylabel("Photon Counts [count]")

		print "---/Binning---"

		return binned_counts, time_bins

	def post_process_correlate(self,voltages,dt,save,plot,group,axes):
		binned_counts,times = self.post_process_binning(voltages=voltages,dt=dt,save=save,plot=plot,group=group,axes=axes[0:-1])
		
		print "---Correlate---"
		#compute originals values:
		autocorrelation = dls_signal_postprocessing.autocorrelation(binned_counts)
		time_bin_width = self.bin_width
		#truncate delay time t=0
		autocorrelation = autocorrelation[1:]
		times = times[1:]

		attrs = attrs = {
			
			"device": "adlink9812",
			"type": "autocorrelation",
			"_units": "none",
			"X label": "Time [s]",
			"Y label": "Intensity Autocorrelation g2 [no units]"
			}
		if save and self.correlate_checkbox.isChecked():
			print "Saving Autocorrelation stage"
			group.create_dataset("autocorrelation",data=[times,autocorrelation], attrs = attrs)
			group.file.flush()

		if plot and self.correlate_checkbox.isChecked():
			axes[-1].semilogx(times,autocorrelation,'x-')
			axes[-1].set_xlabel("Time [s]")
			axes[-1].set_ylabel("Autocorrelation g2 [no units]")

		print "---/Correlate---"


		return times, autocorrelation

		

	def capture(self):
		
		save = self.save_checkbox.isChecked()
		plot = self.plot_checkbox.isChecked()

		print "-"*5+"Adlink 9812: Capture" + "-"*5
		print "SamplingFreq (Hz):", self.sample_freq
		print "SampleCount (counts):", self.sample_count
		print "SeriesName: ", self.series_group
		print "Plot trace:", plot
		print "Save trace:", save
		if save:
			try:
				self.datafile
			except AttributeError:
				self.datafile = nplab.datafile.current()
			dg = self.datafile.require_group(self.series_group)
		else:
			dg = None
		
		#capture voltages
		voltages, dt = self.card.capture(sample_freq=self.sample_freq, sample_count=self.sample_count)
		
		checkboxes = [self.correlate_checkbox,self.binning_checkbox,self.difference_checkbox,self.raw_checkbox]
		checked = np.sum([1 for checkbox in checkboxes if checkbox.isChecked()==True])
		if checked < 2:
			fig,axes = plt.subplots(checked)
			if checked == 1:
				axarr = [axes]
			else:
				axarr = axes
		else:
			rows = 2
			cols = int(math.ceil(checked/2.0))
			fig,axes = plt.subplots(rows,cols,squeeze=True)

			axarr = np.reshape(axes,rows*cols)
			# for i in range(rows):
			# 	for j in range(cols):
			# 		axarr.append(axes[i,j])
		
		times, autocorrelation = self.post_process_correlate(voltages=voltages,dt=dt,save=save,group=dg,plot=plot,axes = axarr)
		if plot:
			plt.legend()
			plt.tight_layout()
			plt.show()
	
		#plot measurement on graph

		# if plot:
			
		# 	fig, axes = plt.subplots(2,2)
			

		# 	sample_times =dt*np.arange(0,len(voltages))
		# 	axarr[0].plot( sample_times,voltages,'x')
		# 	axarr[0].set_xlabel("Time [s]")
		# 	axarr[0].set_ylabel("Voltage [V]")

		# 	axarr[1].plot(dt*np.arange(0,len(diff)),diff,'x')
		# 	axarr[1].set_xlabel("Time [s] (interval lower bound)")
		# 	axarr[1].set_ylabel("Voltage difference [V]")

		# 	# axarr[2].plot(dt*np.arange(0,len(thresholded)),thresholded,'x-')
		# 	# axarr[2].set_xlabel("Time [s] (interval lower bound)")
		# 	# axarr[2].set_ylabel("Thresholded difference [values $\in \{0,1\}]$")

		# 	axarr[2].plot(time_bins,binned,'x-')
		# 	axarr[2].set_xlabel("Time [s] (time bin lower bound)")
		# 	axarr[2].set_ylabel("Photon Counts [count]")
			
		# 	axarr[3].semilogx(times,autocorrelation,'x-')
		# 	axarr[3].set_xlabel("Time [s]")
		# 	axarr[3].set_ylabel("Autocorrelation g2 [no units]")

		# 	plt.tight_layout()

		# 	total_counts = np.sum(np.absolute(diff))
		# 	T = np.max(sample_times)
		# 	print "TOTAL COUNTS",total_counts
		# 	print "Sampling Time:",T
		# 	print "RATE:", float(total_counts)/float(T)
		# 	plt.show()			
			# print voltages
			# self.plot_series(voltages=voltages, dt=dt, timestamp=timestamp)
		
		return

if __name__ == "__main__":
	
	#debug mode enabled - won't try to picj up card - will generate data
	card = Adlink9812("C:\ADLINK\PCIS-DASK\Lib\PCI-Dask64.dll",debug=True)
	app = get_qt_app()
	ui = Adlink9812UI(card=card,debug =False)
	ui.show()
	sys.exit(app.exec_())