# -*- coding: utf-8 -*-
"""
First created on Thu Feb 01 13:21:40 2018

@author: Charlie Readman
"""
if __name__ == '__main__':
    print 'Importing modules...'

import h5py
import numpy as np
import os
import matplotlib.pyplot as plt
from scipy import sparse
import scipy.sparse.linalg as splu
from scipy.signal import butter, filtfilt
from lmfit.models import GaussianModel
import time
from PIL import Image
from random import randint
import scipy.optimize as spo

if __name__ == '__main__':
    absolute_start_time = time.time()
    print 'Modules imported\n'
    print 'Initialising functions...'

'''OBJECTS'''

class DF_Spectrum(object):

    def __init__(self, intensities, fitParams, isNpom, isDouble, cmPeakPos, metadata):
        self.intensities = intensities #y data (1D array)
        self.fitParams = fitParams #parameters that describe the multiple gaussians that make up each spectrum (dictionary)
        self.isNpom = isNpom #Whether or not the spectrum describes an NPoM (bool)
        self.isDouble = isDouble #Whether or not the spectrum contains a double coupled mode (bool)
        self.cmPeakPos = cmPeakPos #What it says on the tin (float)
        metadataKeys = ['NPoM?',
                      'double_peak?',
                      'transverse_mode_position',
                      'transverse_mode_intensity',
                      'coupled_mode_position',
                      'coupled_mode_intensity',
                      'intensity_ratio',
                      'raw_data',
                      'normalised_spectrum',
                      'full_wavelengths',
                      'truncated_spectrum',
                      'smoothed_spectrum',
                      'initial_guess',
                      'best_fit',
                      'residuals',
                      'final_components',
                      'final_params',
                      'truncated_wavelengths',
                      'second_derivative']

        if metadata == 'N/A':
            self.metadata = {key : 'N/A' for key in metadataKeys}

        else:
            self.metadata = metadata #All other relevant info (dictionary)

'''FUNCTIONS'''

def retrieveData(summaryFile, startSpec, finishSpec):

    '''Retrieves data from summary file'''

    try:
        summaryFile = h5py.File('%s.h5' % summaryFile, 'r')

    except:

        try:
            summaryFile = h5py.File('%s.hdf5' % summaryFile, 'r')

        except:
            print 'Summary file not found'
            return

    allScans = summaryFile['particleScanSummaries/']
    spectraLengths = []

    for scan in allScans:

        if len(allScans[scan]) != 0:
            spectraLengths.append(len(allScans[scan]['spectra']))

        else:
            spectraLengths.append(0)

    scanNumber = np.array(spectraLengths).argmax()

    if finishSpec == 0:
        spectra = summaryFile['particleScanSummaries/scan%s/spectra' % scanNumber][()][startSpec:]

    else:
        spectra = summaryFile['particleScanSummaries/scan%s/spectra' % scanNumber][()][startSpec:finishSpec]

    wavelengths = summaryFile['particleScanSummaries/scan%s/spectra' % scanNumber].attrs['wavelengths'][()]
    background = summaryFile['particleScanSummaries/scan%s/spectra' % scanNumber].attrs['background'][()]
    reference = summaryFile['particleScanSummaries/scan%s/spectra' % scanNumber].attrs['reference'][()]

    summaryFile.close()

    print 'Data retrieved from particleScanSummaries/scan%s\n' % scanNumber
    return spectra, wavelengths, background, reference

def findKey(inputDict, value):
    return next((k for k, v in inputDict.items() if v == value), None)

def removeNaNs(spectrum):
    '''Removes NaN values'''
    #Identifies NaN values and sets the corresponding data point as an average of the two either side
    #If multiple sequential NaN values are encountered a straight line is made between the two closest data points
    #Input = 1D array
    #Works like list.sort() rather than sorted(list), i.e. manipulates array directly rather than returning a new one
    '''A bit clunky; will rewrite at some point'''

    i = -1

    if not np.isfinite(spectrum[i]) == True:

        while not np.isfinite(spectrum[i]) == True:
            i -= 1

        for j in range(len(spectrum[i:])):
            spectrum[i+j] = spectrum[i]

    for i in range(len(spectrum)):

        if not np.isfinite(spectrum[i]) == True:

            if i == 0:
                j = i

                while not np.isfinite(spectrum[j]) == True:
                    j += 1

                for k in range(len(spectrum[i:j])):
                    spectrum[i+k] = spectrum[j]

            elif i != len(spectrum) - 1:
                j = i

                while not np.isfinite(spectrum[j]) == True:
                    j += 1

                start = spectrum[i-1]
                end = spectrum[j]
                diff = end - start

                for k in range(len(spectrum[i:j])):
                    spectrum[i+k] = float(start) + float(k)*float(diff)/(len(spectrum[i:j]))

def correctSpectrum(spectrum, reference):
    #Removes any NaNs from all spectra in list and divides each by a 1D array of the same length (designed for referencing)
    #spectra = list of arrays, 2D array with size (n, 1)
    #reference = 1D array

    for n in range(len(reference)):

        if reference[n] == 0.:
            reference[n] = np.nan

    removeNaNs(reference)
    return spectrum/reference

def printEnd():
    print '%sDONE' % ('\n' * randint(0, 12))

    print '%s%s%sv gud' % ('\t' * randint(0, 12), '\n' * randint(0, 5), ' ' * randint(0, 4))

    print '%s%ssuch python' % ('\n' * randint(0, 5), ' ' * randint(0, 55))
    print '%s%smany spectra' % ('\n' * randint(0, 5), ' ' * randint(10, 55))
    print '%s%smuch fitting' % ('\n' * randint(0, 5), ' ' * randint(8, 55))
    print '%s%swow' % ('\n' * randint(2, 5), ' ' * randint(5, 55))
    print '\n' * randint(0, 7)

def prepareData(spectra, wavelengths, reference):
    '''Removes NaN values from and references spectra'''
    #spectra = list of 1D arrays
    #wavelengths = 1D array or list
    #reference = 1D array or list

    prepStart = time.time()

    '''INITIAL FIT PARAMETERS'''

    print 'Preparing data...'

    removeNaNs(wavelengths)

    for spectrum in spectra:
        removeNaNs(spectrum)

    referencedSpectra = [correctSpectrum(spectrum, reference) for spectrum in spectra]

    prepEnd = time.time()
    prepTime = prepEnd - prepStart

    print '%s spectra cleared of NaNs and referenced in %s seconds\n' % (len(spectra), prepTime)

    return wavelengths, referencedSpectra

def createOutputFile(filename):

    '''Auto-increments new filename if file exists'''

    print 'Creating output file...'

    outputFile = '%s.h5' % filename

    if outputFile in os.listdir('.'):
        print '\n%s already exists' % outputFile
        n = 0
        outputFile = '%s_%s.h5' % (filename, n)

        while outputFile in os.listdir('.'):
            print '%s already exists' % outputFile
            n += 1
            outputFile = '%s_%s.h5' % (filename, n)

    print '\nOutput file %s created' % outputFile
    return outputFile

def truncateSpectrum(wavelengths, spectrum, startWl = 450, finishWl = 900):
    #Truncates spectrum within a certain wavelength range. Useful for removing high and low-end noise

    for n, wl in enumerate(wavelengths):

        if n == 0 and wl > startWl:
            startIndex = n

        if int(np.round(wl)) == int(np.round(startWl)):
            startIndex = n

        elif int(np.round(wl)) == int(np.round(finishWl)):
            finishIndex = n

        elif n == len(wavelengths) - 1 and wl < finishWl:
            finishIndex = n

    wavelengthsTrunc = np.array(wavelengths[startIndex:finishIndex])
    spectrumTrunc = np.array(spectrum[startIndex:finishIndex])
    return np.array([wavelengthsTrunc, spectrumTrunc])

def baselineAls(y, lambd, p, iterations = 10):
    '''Calculates baseline for data
    lambd ~ 10^n
    p ~10^(-m)'''

    L = y.size
    D = sparse.csc_matrix(np.diff(np.eye(L), 2))
    w = np.ones(L)
    for i in xrange(iterations):
        W = sparse.spdiags(w, 0, L, L)
        Z = W + lambd * D.dot(D.transpose())
        z = splu.spsolve(Z, w*y)
        w = p * (y > z) + (1-p) * (y < z)
    return z

def butterLowpassFiltFilt(data, cutoff = 1500, fs = 60000, order=5):
    '''Smoothes data without shifting it'''
    nyq = 0.5 * fs
    normalCutoff = cutoff / nyq
    b, a = butter(order, normalCutoff, btype='low', analog=False)
    yFiltered = filtfilt(b, a, data)
    return yFiltered

def detectMinima(y, negOnly = True, threshold = 0):
    '''Finds and returns list of minima in a data set'''
    ind = False

    ySign = np.sign(y + threshold)
    dy = np.zeros(len(y))
    dy[1:] = np.diff(y)

    if len(dy) > 1:
        dy[0] = dy[1]
        dy = np.sign(dy)
        d2y = np.zeros(len(y))
        d2y[1:] = np.diff(dy)
        d2y[0] = d2y[1]
        d2y = np.sign(d2y)

        if negOnly == True:
            '''Finds only minima that exist below zero'''
            ind = np.nonzero((-ySign + dy + d2y) == 3)
            ind = ind[0]
            ind = [int(i) for i in ind]

        elif negOnly == False:
            '''Finds all minima'''
            ind = np.nonzero((dy + d2y) == 2)
            ind = ind[0]
            ind = [int(i) for i in ind]

        return ind

def testIfNpom(x, y, lower = 0.1, upper = 2.5, NpomThreshold = 1.9):
    '''Filters out spectra that are obviously not from NPoMs'''

    isNpom = False #Guilty until proven innocent

    '''To be accepted as an NPoM, you must first pass three trials'''

    x = np.array(x)
    y = np.array(y)

    [xTrunc, yTrunc] = truncateSpectrum(x, y)
    [xUpper, yUpper] = truncateSpectrum(x, y, startWl = 900, finishWl = x.max())

    '''Trial the first: do you have a reasonable signal?'''

    if np.sum(yTrunc) > lower and np.sum(yTrunc) < upper:
        #If sum of all intensities lies outside a given range, it's probably not an NPoM
        #Can adjust range to suit system
        firstHalf = yTrunc[:int(len(yTrunc)/2)]
        secondHalf = yTrunc[int(len(yTrunc)/2):]

        '''Trial the second: do you slant in the correct direction?'''

        if np.sum(firstHalf) < np.sum(secondHalf) * NpomThreshold:
            #NPoM spectra generally have greater total signal at longer wavelengths due to coupled mode

            '''Trial the third: are you more than just noise?'''

            if np.sum(yTrunc) > np.sum(yUpper) / NpomThreshold:
                #If the sum of the noise after 900 nm is greater than that of the spectrum itself, it's probably crap

                isNpom = True

    return isNpom

def take_derivs(y, x):
    '''Numerically differentiates y wrt x twice and returns both derivatives'''
    #y, x = 1D array

    dy = np.diff(y)
    dx = np.diff(x)
    first_derivative = dy/dx

    d_dy_dx = np.diff(first_derivative)

    second_derivative = d_dy_dx/dx[:-1]

    return first_derivative, second_derivative

def remove_baseline(x, y, cutoff = 1500, fs = 60000, lambd = 10**6.7, p = 0.003, return_trunc = False):
    '''Specifically designed for NPoM spectra'''

    x_raw = x
    y_raw = y

    x_trunc1, y_trunc1 = truncateSpectrum(x_raw, y_raw, startWl = 450, finishWl = 1000) #Truncate to remove low-end noise
    y_trunc1_smooth = butterLowpassFiltFilt(y_trunc1, cutoff, fs) #Smooth truncated data
    y_trunc1_minima = detectMinima(y_trunc1_smooth, negOnly = False) #Finds indices of minima in smoothed data

    init_min_index = y_trunc1_minima[0] #Index of first minimum in truncated spectrum
    init_wl = x_trunc1[init_min_index] #Wavelength corresponding to this minimum
    init_min_index = np.where(x_raw == init_wl)[0][0] #Corresponding index in full spectrum

    x_trunc2, y_trunc2 = truncateSpectrum(x_raw, y_raw, startWl = 800, finishWl = 1100) #Truncate to only probe data after CM peak
    y_trunc2_smooth = butterLowpassFiltFilt(y_trunc2, cutoff, fs) #Smooth truncated data
    y_trunc2_minima = detectMinima(y_trunc2_smooth, negOnly = False) #Finds indices of minima in smoothed data

    final_min_index = y_trunc2_minima[0] #Index of first minimum after CM peak
    final_wl = x_trunc2[final_min_index] #Wavelength corresponding to this minimum
    final_min_index = np.where(x_raw == final_wl)[0][0] #Corresponding index in full spectrum

    '''These two minima are taken as the start and end points of the "real" spectrum'''

    x_trunc3, y_trunc3 = truncateSpectrum(x_raw, y_raw, startWl = init_wl, finishWl = final_wl) #Truncate spectrum between two minima
    y_trunc3_baseline = baselineAls(y_trunc3, lambd, p) #Take baseline of this data
    y_trunc3_subtracted = y_trunc3 - y_trunc3_baseline

    '''Baseline extrapolated with straight line at each end so it can be subtracted from the raw spectrum'''

    y_baseline_1 = [y_trunc3_baseline[0]] * init_min_index
    y_baseline_2 = [i for i in y_trunc3_baseline]
    y_baseline_3 = [y_trunc3_baseline[-1]] * (len(y_raw) - final_min_index)

    y_full_baseline = y_baseline_1 + y_baseline_2 + y_baseline_3

    '''Due to rounding errors when truncating, extrapolated baseline may have different length to raw data '''

    len_diff = len(y_raw) - len(y_full_baseline) #Calculate this difference

    if len_diff < 0:
        y_full_baseline = y_full_baseline[:len_diff] #Remove data point(s) from end if necessary

    elif len_diff > 0:

        for j in range(len_diff):
            y_full_baseline.append(y_trunc3_baseline[-1]) #Add data point(s) to end if necessary

    y_full_baseline = np.array(y_full_baseline)
    y_subtracted = y_raw - y_full_baseline #Subtract baseline from raw data

    '''Baseline calculation isn't perfect, so this subtraction sometimes leads to unrealistically negative y-values'''
    '''Data truncated and smoothed once more, and minimum subtracted from data'''

    subtracted_trunc = truncateSpectrum(x_raw, y_subtracted, startWl = 450, finishWl = 850)
    y_sub_trunc = subtracted_trunc[1]
    y_sub_trunc_smooth = butterLowpassFiltFilt(y_sub_trunc, cutoff, fs)

    y_subtracted -= y_sub_trunc_smooth.min()

    if return_trunc == True:
        return y_subtracted, x_trunc3, y_trunc3_subtracted

    else:
        return y_subtracted

def norm_to_trans(x, y, cutoff = 1500, fs = 60000, lambd = 10**6.7, p = 0.003, plot = False, monitor_progress = False, baseline = True, return_peakpos = True):
    '''Specifically for use with NPoM spectra'''
    '''Finds the first shoulder in the spectrum after 500 nm and normalises the spectrum to the corresponding intensity'''

    x_raw = x
    y_raw = y

    if baseline == True:
        y_subtracted, x_trunc, y_trunc = remove_baseline(x_raw, y_raw, lambd = lambd, p = p, return_trunc = True)#Baseline subtraction if requested

    else:
        x_trunc, y_trunc = truncateSpectrum(x_raw, y_raw, startWl = 450, finishWl = 900)#Otherwise just truncated to standard range

    y_trunc_smooth = butterLowpassFiltFilt(y_trunc, cutoff = cutoff, fs = fs)#Smooth data
    first_deriv, second_deriv = take_derivs(y_trunc_smooth, x_trunc)#Take second derivative

    peak_indices = detectMinima(second_deriv, negOnly = False)#Detect minima in second derivative to find spectral peaks/shoulders

    x_peaks = [x_trunc[index] for index in peak_indices]#Peak positions

    for n, peak_wl in enumerate(x_peaks):

        if peak_wl > 500:
            trans_index = peak_indices[n]#Finds index of first peak after x=500 - most likely the transverse mode
            break

    trans_wl = x_trunc[trans_index]
    trans_height = y_trunc_smooth[trans_index] #Corresponding x and y values

    if baseline == False: #Sets the spectral minimum to zero
        y_subtracted = y_raw - min(y_trunc_smooth)
        y_trunc = y_trunc - min(y_trunc_smooth)

    y_norm = y_subtracted / trans_height
    y_trunc_norm = y_trunc / trans_height #Normalisation

    if return_peakpos == True:
        return y_norm, trans_wl, x_trunc, y_trunc_norm#Returns transverse peak position along with normalised data, if requested

    else:
        return y_norm, x_trunc, y_trunc_norm

def multiPeakFind(x, y, cutoff = 1500, fs = 60000, detection_threshold = 0, return_all = True, monitor_progress = False):

        '''Finds spectral peaks (including shoulders) by smoothing and then finding minima in the second derivative'''

        peakFindMetadata = {}

        y_smooth = butterLowpassFiltFilt(y, cutoff = cutoff, fs = fs)
        peakFindMetadata['smoothed_spectrum'] = y_smooth

        if monitor_progress == True:
            print '\nData smoothed'

        '''Differentiation'''

        first_derivative, second_derivative = take_derivs(y_smooth, x)
        peakFindMetadata['second_derivative'] = second_derivative

        if monitor_progress == True:
            print 'Derivatives taken'

        '''Peak detection in 2nd derivative'''

        peakIndices = detectMinima(second_derivative, negOnly = True, threshold = second_derivative.max()*detection_threshold)

        if monitor_progress == True:
            print '%s peaks detected' % (len(peakIndices))

        if return_all == True:
            return y_smooth, peakIndices, peakFindMetadata

def multiPeakFit(x, y, indices, y_smooth = np.array([]), cutoff = 1500, fs = 60000, constrain_peakpos = False, return_all = False, monitor_progress = True):
    '''Performs the actual fitting (given a list of peak indices) using Python's lmfit module'''
    '''You can generate indices using multiPeakFind or input them manually'''
    #x, y = 1D arrays of same length
    #indices = 1D array or list of integers, to be used as indices of x and y
    #y_smooth (optional). Include this to save time, otherwise the function will smooth the y data for you
    #setting constrain_peakpos = True forces peaks to stay between the indices either side when fitting
    #e.g. for indices of [7, 10, 14], the final centre position of the second peak (initial index = 10) must be between index 7 and 14

    fit_start = time.time()
    peakFitMetadata = {}

    if y_smooth.size == 0:
        y_smooth = butterLowpassFiltFilt(y, cutoff = cutoff, fs = fs) #smoothes data

    if monitor_progress == True:
        print '\n%s peaks about to be fitted' % (len(indices))

    model_elements = [] #Empty list to be populated with components of model
    component = GaussianModel(prefix = 'g0_')
    component.set_param_hint('amplitude', min = 0)
    component.set_param_hint('center', min = x.min(), max = 850) #Above 850 is v. noisy, so NO PEAKS ALLOWED
    model_elements.append(component) #One gaussian added for starters

    if len(indices) == 1: #If only one peak detected
        pars = model_elements[0].guess(y_smooth, x = x) #initial parameter guess based on entire spectrum
        gauss_model = model_elements[0] #total model set equal to gaussian component

    else: #If more than one peak detected
        #Sets data range for first peak initial guess
        peak_end = int((indices[0] + indices[1])/2) #Midpoint between 1st and 2nd peak taken as end of data range for 1st peak
        pars = model_elements[0].guess(y_smooth[:peak_end], x[:peak_end]) #initial guess performed within this range
        gauss_model = model_elements[0] #total model initially set equal to first gaussian component

        if constrain_peakpos == True:
            model_elements[0].set_param_hint('center', max = x[peak_end])

        for i in range(len(indices))[1:]:
            component = GaussianModel(prefix = 'g%s_' % (i))
            component.set_param_hint('amplitude', min = 0)
            component.set_param_hint('center', min = x.min(), max = 850) #Above 850 is v. noisy, so NO PEAKS ALLOWED
            model_elements.append(component) #Components list populated with appropriate number of gaussians to be calculated

            if i > 0 and i != len(indices) - 1: #Sets initial guess data range for subsequent peaks
                peak_start = int((indices[i - 1] + indices[i])/2)
                peak_end = int((indices[i] + indices[i + 1])/2)

            elif i > 0 and i == len(indices) - 1: #Sets initial guess data range for final peak
                peak_start = int((indices[i - 1] + indices[i])/2)
                peak_end = len(x)

            if constrain_peakpos == True:
                model_elements[i].set_param_hint('center', min = x[peak_start + 1], max = x[peak_end - 1])

            pars.update(model_elements[i].guess(y_smooth[peak_start:peak_end], x[peak_start:peak_end]))#List of parameters updated with initial guesses for each peak
            gauss_model += model_elements[i]#Total model updated to include each subsequent peak

    if monitor_progress == True:
        print 'Initial guesses made for %s gaussians' % (len(indices))

    init = gauss_model.eval(pars, x=x)#Function formed from initial guesses

    peakFitMetadata['initial_guess'] = init

    y_float16 = np.float16(y) #Reduces the number of decimal places in data to speed up fitting
    x_float16 = np.float16(x)

    out = gauss_model.fit(y_float16, pars, x=x_float16) #Performs the fit, based on initial guesses

    #out = gauss_model.fit(y_smooth, pars, x=x) #Can fit to smoothed data instead if you like
    comps = out.eval_components(x=x_float16)
    peakFitMetadata['final_components'] = comps

    fit_end = time.time()
    fit_time = fit_end - fit_start

    if monitor_progress == 'time' or monitor_progress == True:
        print '\n\nFit performed in %s seconds' % fit_time

    if monitor_progress == True:
        print '%s components' % len(comps)
        print '\nFit performed'

    final_params = {}
    component_param_names = ['sigma', 'center', 'amplitude', 'fwhm', 'height', 'wavelengths']

    for prefix in [model.prefix for model in model_elements]:
        final_params[prefix[:-1]] = {}

        for name in component_param_names:

            if name != 'wavelengths':
                final_params[prefix[:-1]][name] = out.params[prefix + name].value

            elif name == 'wavelengths':
                final_params[prefix[:-1]][name] = x

    peakFitMetadata['lmfit_output'] = out
    peakFitMetadata['best_fit'] = out.best_fit
    peakFitMetadata['final_params'] = final_params
    peakFitMetadata['residuals'] = out.residual

    if return_all == True:
        return out, peakFitMetadata

    else:
        return out

def test_if_double(x, ySmooth, final_params, doubles_threshold = 0.5, min_dist = 30, monitor_progress = False, plot = False, return_all = True):

    '''Decides if DF spectrum contains two coupled modes. Requires fitting beforehand. Sloppy but gets the job done.
    May tidy up later'''

    #x = 1D array
    #ySmooth = smoothed yData
    #final_params = dictionary of parameters that describe the multiple gaussians that make up each spectrum, as returned by find_fit_peaks (see below)
    #doubles_threshold = minimum size ratio required to classify a double resonance

    is_double = False #Innocent until proven guilty
    heights = [] #List to be populated with peak heights
    centers = [] #List to be populated with peak positions
    component_numbers = []

    for n in range(len(final_params)):

        if final_params['g%s' % (n)]['center'] > 575: #Excludes tranverse peak
            heights.append(final_params['g%s' % (n)]['height']) #Populates list of heights
            centers.append(final_params['g%s' % (n)]['center'])
            component_numbers.append(n)

    heights_sorted = sorted(heights)
    centers_sorted = [c for _,c in sorted(zip(heights, centers))]

    peak_1_index = 0
    peak_2_index = 0

    if len(centers_sorted) > 1:
        #Only performs the analysis if more than 1 peak exists

        for n in range(len(x)):

            if int(x[n]) == int(centers_sorted[-1]):
                peak_1_index = n

            if int(x[n]) == int(centers_sorted[-2]):
                peak_2_index = n

            if peak_1_index != 0 and peak_2_index != 0:
                break

        if peak_1_index > peak_2_index:
            x_CM = x[peak_2_index:peak_1_index]
            y_CM = ySmooth[peak_2_index:peak_1_index]

        else:
            x_CM = x[peak_1_index:peak_2_index]
            y_CM = ySmooth[peak_1_index:peak_2_index]

        if monitor_progress == True and plot == 'all':
            print 'Region between maxima:'
            plt.plot(x_CM, y_CM)
            plt.show()

        if len(heights) > 1:

            if heights_sorted[-1] * doubles_threshold < heights_sorted[-2]:
                '''If height of second largest peak > (largest peak x chosen threshold)'''

                if monitor_progress == True:
                    print '\tSecond peak is bigger than %s times the size of the largest' % doubles_threshold

                if abs(centers_sorted[-1] - centers_sorted[-2]) > min_dist:
                    '''AND peaks are more than a certain distance apart'''

                    CM_minima_indices = detectMinima(y_CM, negOnly = False)

                    if monitor_progress == True:
                        print '\t peaks are further than %s nm apart' % min_dist
                        print 'Region between maxima:'

                        plt.plot(x_CM, y_CM)
                        plt.show()

                    if len(CM_minima_indices) > 0:
                        '''AND a minimum exists between them'''

                        x_mins = [x_CM[index] for index in CM_minima_indices]
                        y_mins = [y_CM[index] for index in CM_minima_indices]

                        if monitor_progress == True:
                            print 'Minimum exists between peaks'

                            plt.plot(x_CM, y_CM)
                            plt.plot(x_mins, y_mins, 'o')
                            plt.show()

                        is_double = True
                        '''it counts as a double peak'''

                    else:

                        if monitor_progress == True:
                            print 'No minumum between peaks'

    if monitor_progress == True:

        if is_double == True:
            print '\nDouble peak'

        elif is_double == False:
            print '\nSingle peak'

    if return_all == True:
        return is_double, heights, centers

    else:
        return is_double

def findTransAndCoupledMode(x, y_smooth, fitParams, transGuess = 533, transRange = [500, 550], plot = False):

    '''Finds CM and transverse peak heights/positions using fit data (dictionary) and smoothed spectrum'''
    '''Returns dictionary of relevant data'''
    tcMetadata = {}
    ySmoothTrunc = truncateSpectrum(x, y_smooth, startWl = 600, finishWl = 850) #Truncates smoothed spectrum to neighbourhood of the coupled mode
    cmHeight = ySmoothTrunc[1].max() #maximum value is likely the coupled mode height
    cmPeakPos = ySmoothTrunc[0][ySmoothTrunc[1].argmax()] #coupled mode wavelength assigned to this

    if int(cmPeakPos) < 601:
        '''If whatever comes before 600 nm is much larger than the coupled mode, then the start of the truncated region may be assigned as the coupled mode'''
        '''If this is the case, the minimum after this is found, and the truncation performed again from this point'''
        newMinimum = detectMinima(ySmoothTrunc, negOnly = False)[0]
        newMinWl = ySmoothTrunc[0][newMinimum]
        ySmoothTrunc = truncateSpectrum(x, y_smooth, startWl = newMinWl, finishWl = 850)
        cmHeight = ySmoothTrunc[1].max()
        cmPeakPos = ySmoothTrunc[0][ySmoothTrunc[1].argmax()]

    tcMetadata['coupled_mode_position'] = cmPeakPos
    tcMetadata['coupled_mode_intensity'] = cmHeight

    for prefix in sorted(fitParams.keys(), key = lambda prefix: int(prefix[1:])):
        '''Identifies the transverse mode among the component gaussian functions'''
        #prefix in the form 'gn'
        comp = fitParams[prefix]#gives dictionary containing parameters of gaussian component

        if transRange[0] < comp['center'] < transRange[1]:#Only wavelengths between 500 and 550 nm are considered
            transPeakPos = comp['center']
            break #Stops after first peak between 500 and 550

        elif comp['center'] > 550:

            transPeakPos = transGuess #If no peaks are detected, initial transverse mode guess (533 nm unless specified otherwise) is used as the final value
            break

    tcMetadata['transverse_mode_position'] = transPeakPos
    transIndex = np.where(abs(x - transPeakPos) == abs(x - transPeakPos).min())[0][0]
    transHeight = y_smooth[transIndex]#Takes height of smoothed spectrum at transverse peak position
    tcMetadata['transverse_mode_intensity'] = transHeight

    intensityRatio = cmHeight/transHeight
    tcMetadata['intensity_ratio'] = intensityRatio

    return tcMetadata

def fitNpomSpectrum(x, y, cutoff = 1500, fs = 60000, lambd = 10**6.7, baseline_p = 0.003, detection_threshold = 0, doubles_threshold = 0.5, doubles_dist = 30, constrain_peakpos = False, print_report = False, plot = False, monitor_progress = False):

    y_raw = np.array(y)
    x_raw = np.array(x)

    all_metadata_keys = ['NPoM?',
                      'double_peak?',
                      'transverse_mode_position',
                      'transverse_mode_intensity',
                      'coupled_mode_position',
                      'coupled_mode_intensity',
                      'intensity_ratio',
                      'raw_data',
                      'normalised_spectrum',
                      'full_wavelengths',
                      'truncated_spectrum',
                      'smoothed_spectrum',
                      'initial_guess',
                      'best_fit',
                      'residuals',
                      'final_components',
                      'final_params',
                      'truncated_wavelengths',
                      'second_derivative']

    metadata = {key : 'N/A' for key in all_metadata_keys}
    metadata['raw_data'] = y_raw
    metadata['full_wavelengths'] = x_raw

    '''Testing if NPoM'''

    is_NPoM = testIfNpom(x_raw, y_raw)
    metadata['NPoM?'] = is_NPoM

    if plot == 'raw' or plot == 'all':
        plt.figure(figsize = (10,7))
        y_max = y_raw[67:661].max()
        y_lim_frac = y_max/10
        plt.ylim(-y_lim_frac, y_max + y_lim_frac)

        if is_NPoM == True:
            plt.plot(x_raw, y_raw, 'g', label = 'Raw Data')

        else:
            plt.plot(x_raw, y_raw, 'r', label = 'Raw Data')

        plt.xlim(x_raw.min(), x_raw.max())
        plt.xlabel('Wavelength (nm)')
        plt.ylabel('Scattering Intensity')
        plt.title('Raw Data\nNPoM = %s' % is_NPoM)
        plt.show()

    if monitor_progress == True:
        print 'NPoM:', is_NPoM

    if is_NPoM == True:

        y_raw_norm, transShoulderPeakPos, x_trunc, y_trunc = norm_to_trans(x, y, cutoff = cutoff, fs = fs, lambd = lambd, p = baseline_p, plot = False, monitor_progress = False, baseline = True)
        metadata['normalised_spectrum'] = y_raw_norm
        metadata['transverse_mode_position'] = transShoulderPeakPos

        x_trunc, y_trunc = truncateSpectrum(x_trunc, y_trunc, startWl = x_trunc[0], finishWl = 850)
        metadata['truncated_spectrum'] = y_trunc
        metadata['truncated_wavelengths'] = x_trunc

        if monitor_progress == True:
            print '\nData baseline subtracted and normalised'

        if plot == 'all':
            plt.figure(figsize = (10,7))
            y_max = y_raw_norm[67:661].max()
            y_lim_frac = y_max/10
            plt.ylim(-0.02, y_max + y_lim_frac)
            plt.plot(x_raw, y_raw_norm, 'purple')
            plt.xlim(x_raw.min(), x_raw.max())
            plt.xlabel('Wavelength (nm)')
            plt.ylabel('Scattering Intensity')
            plt.title('Baselined/Normalised Data')
            plt.show()

        y_smooth, indices, peakFindMetadata = multiPeakFind(x_trunc, y_trunc, cutoff = 1500, fs = 60000, detection_threshold = 0, return_all = True, monitor_progress = False)
        metadata.update(peakFindMetadata)

        '''Reassignment of x and y below is v. important'''

        y = y_trunc
        x = x_trunc

        if len(indices) != 0:
            out, peakFitMetadata = multiPeakFit(x, y, indices, y_smooth = y_smooth, cutoff = 1500, fs = 60000, return_all = True, monitor_progress = monitor_progress, constrain_peakpos = constrain_peakpos)
            metadata.update(peakFitMetadata)

            is_double, peakHeights, peakCenters = test_if_double(x, y_smooth, metadata['final_params'], doubles_threshold = doubles_threshold, min_dist = doubles_dist, monitor_progress = monitor_progress)
            metadata['double_peak?'] = is_double

            if monitor_progress == True:
                print 'Fitting complete'

            if print_report == True:
                print 'Fit report:\n'
                print out.fit_report()

            if plot == 'basic' or plot == 'both':
                plt.figure(figsize = (10,7))
                plt.plot(x_raw, y_raw_norm, label = 'raw')
                plt.plot(x, out.best_fit, 'r-', label = 'fit')
                plt.legend(loc = 0)
                plt.xlabel('Wavelength (nm)')
                plt.tick_params(axis = 'y', labelleft = 'off')
                plt.ylabel('Intensity')
                plt.xlim(450, 1050)
                plt.show()

            elif plot == 'full' or plot == 'all':

                plt.figure(figsize = (10,7))

                if monitor_progress == True:

                    if is_double == True:
                        plt.title('Double Peak')

                    elif is_double == False:
                        plt.title('Single Peak')

                plt.plot(x_raw, y_raw_norm, label = 'raw', linewidth = 0.7)
                plt.plot(x, y_smooth, label = 'smoothed', linewidth = 0.5)
                plt.plot(x, metadata['initial_guess'], 'k-', label = 'initial guess', linewidth = 0.3)

                for i in range(len(indices)):
                    plt.plot(x, metadata['final_components']['g%s_' % (i)], '--', label = 'Component %s' % (i), linewidth = 0.3)

                plt.plot(x, out.best_fit, 'r-', label = 'fit')
                plt.legend(loc = 0, ncol = 2, fontsize = 9)
                plt.xlabel('Wavelength (nm)')
                #plt.tick_params(axis = 'y', labelleft = 'off')
                plt.ylabel('Intensity')
                lim_frac = y_smooth.max()/10
                plt.ylim(-lim_frac/2, y_smooth.max() + lim_frac)
                plt.xlim(450, 900)
                plt.yticks([])
                plt.show()

                plt.figure(figsize = (10, 4))
                plt.title('Residuals')
                plt.plot(x, out.residual)
                plt.xlabel('Wavelength (nm)')
                plt.ylabel('Residuals')
                plt.yticks([])
                plt.xlim(450, 900)
                plt.show()

            #if is_double == False:

            tcMetadata = findTransAndCoupledMode(x, y_smooth, metadata['final_params'], transGuess = transShoulderPeakPos, plot = plot)
            metadata.update(tcMetadata)
            transHeight = metadata['transverse_mode_intensity']

            y_smooth /= transHeight
            y_trunc /= transHeight
            y_raw_norm /= transHeight

            metadata['smoothed_spectrum'] = y_smooth
            metadata['truncated_spectrum'] = y_trunc
            metadata['normalised_spectrum'] = y_raw_norm

            if plot == 'all':
                lim_frac = y_smooth.max()/10

                plt.plot(x_raw, y_raw_norm, lw = 0.5)
                plt.plot(x, y)
                plt.plot(x, y_smooth)
                plt.plot(x, [0] * len(x), '--')
                plt.plot([metadata['transverse_mode_position']] * 10, np.linspace(transHeight, metadata['coupled_mode_intensity'], 10), 'k--')
                plt.plot(x, [metadata['coupled_mode_position']] * len(x))
                plt.plot(x, [transHeight] * len(x))
                plt.title('Intensity Ratio: %s' % (metadata['intensity_ratio']))
                plt.xlabel('Wavelength(nm)')
                plt.ylabel('Intensity')
                plt.ylim(-lim_frac/2, y_smooth.max() + lim_frac)
                plt.xlim(450, 900)
                plt.show()

        else:
            metadata['NPoM?'] = False

            if monitor_progress == True:
                print 'Not a NPoM'

            metadata['NPoM?'] = is_NPoM
            return DF_Spectrum(y, 'N/A', is_NPoM, 'N/A', 'N/A', metadata)

    else:

        if monitor_progress == True:
            print 'Not a NPoM'

        metadata['NPoM?'] = is_NPoM

    return metadata

def reduceNoise(y, factor = 10):
    ySmooth = butterLowpassFiltFilt(y)
    yNoise = y - ySmooth
    yNoise /= factor
    y = ySmooth + yNoise
    return y

def plotHistogram(outputFile, startWl = 450, endWl = 900, binNumber = 80, plot = True, minBinFactor = 5, closeFigures = False):

    print '\nCombining spectra and plotting histogram...'
    spectra = outputFile['Fitted spectra']

    n = 0
    x = spectra['Spectrum %s' % n]['Raw/Raw data (normalised)'].attrs['wavelengths']

    while type(x) == str:
        n += 1
        x = spectra['Spectrum %s' % n]['Raw/Raw data (normalised)'].attrs['wavelengths']

    spectraNames = [spectrum for spectrum in spectra if spectrum[:8] == 'Spectrum']

    binSize = (endWl - startWl) / binNumber
    bins = np.linspace(startWl, endWl, num = binNumber)
    frequencies = np.zeros(len(bins))

    startIndex = np.where(np.round(x) == np.round(startWl))[0][0]
    endIndex = np.where(np.round(x) == np.round(endWl))[0][0]

    yDataBinned = [np.zeros(len(x)) for f in frequencies]

    for n, spectrum in enumerate(spectraNames):

        #print spectrum

        for nn, binStart in enumerate(bins):

            #print [attr for attr in spectra[spectrum].attrs]

            cmPeakPos = spectra[spectrum].attrs['Coupled mode wavelength']
            #print cm_peakpos
            yData = spectra[spectrum]['Raw/Raw data (normalised)']

            if cmPeakPos != 'N/A' and binStart < cmPeakPos < binStart + binSize and 600 < cmPeakPos < 850:
                frequencies[nn] += 1
                yDataBinned[nn] += yData

    for n, yDataSum in enumerate(yDataBinned):
        yDataBinned[n] /= frequencies[n]

    if minBinFactor == 0:
        min_bin = 0

    else:
        min_bin = max(frequencies)/minBinFactor

    fig = plt.figure(figsize = (8, 6))

    if plot == True:
        fig = plt.figure(figsize = (8, 6))

        cmap = plt.get_cmap('jet')

        ax1 = fig.add_subplot(111)
        ax1.set_zorder(1)
        ax2 = ax1.twinx()
        ax2.set_zorder(0)
        ax1.patch.set_visible(False)

        ymax = 0

        yDataPlot = []
        freqsPlot = []
        binsPlot = []

        for n, yDatum in enumerate(yDataBinned):

            if frequencies[n] > min_bin:
                yDataPlot.append(yDatum)
                freqsPlot.append(frequencies[n])
                binsPlot.append(bins[n])

        colors = [cmap(256 - n*(256/len(yDataPlot))) for n, yDataSum in enumerate(yDataPlot)][::-1]

        for n, yDataSum in enumerate(yDataPlot):

            current_ymax = yDataSum[startIndex:endIndex].max()

            y_smooth = reduceNoise(yDataSum, factor = 7)
            ax1.plot(x, y_smooth, lw = 0.7, color = colors[n])

            if current_ymax > ymax:
                ymax = current_ymax

        ax1.set_ylim(-0.1, ymax*1.2)
        ax1.set_ylabel('Normalised Intensity', fontsize = 18)
        ax1.tick_params(labelsize = 15)
        ax1.set_xlabel('Coupled Mode Peak Position (nm)', fontsize = 18)
        #ax1.set_xticks(range(500, 900, 50))
        ax2.bar(bins, frequencies, color = 'grey', width = 0.8*binSize, alpha = 0.8, linewidth = 0.6)
        ax2.bar(binsPlot, freqsPlot, color = colors, width = 0.8*binSize, alpha = 0.4, linewidth = 1)
        ax2.set_xlim(startWl, endWl)
        ax2.set_ylim(0, max(frequencies)*1.05)
        ax2.set_ylabel('Frequency', fontsize = 18, rotation = 270)
        ax2.yaxis.set_label_coords(1.11, 0.5)
        ax2.set_yticks([int(tick) for tick in ax2.get_yticks() if tick > 0][:-1])
        ax2.tick_params(labelsize = 15)

        fig.tight_layout()
        fig.savefig('Histogram.png', bbox_inches = 'tight')

        if closeFigures == True:
            plt.close(fig)

        img = Image.open('Histogram.png')
        img = np.array(img)
        img = img.transpose((1, 0, 2))

    return frequencies, bins, yDataBinned, img

def histyFit(frequencies, bins):

    gauss_model = GaussianModel()
    pars = gauss_model.guess(frequencies, x = bins)
    out = gauss_model.fit(frequencies, pars, x=bins)#Performs the fit, based on initial guesses
    print '\nAverage peakpos:', out.params['center'].value, '+/-', out.params['center'].stderr, 'nm'
    print 'FWHM:', out.params['fwhm'].value, 'nm'
    #print out.fit_report()

    resonance = out.params['center'].value
    stderr = out.params['center'].stderr
    fwhm = out.params['fwhm'].value

    return resonance, stderr, fwhm

def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False

def createDensityArray(x, y, xBins = 20, yBins = 20):
    '''Author: Jack Griffiths'''

    array, xEdges, yEdges = np.histogram2d(x, y, [xBins, yBins])
    xCentres=[]
    yCentres=[]

    for i in range(len(xEdges))[1:]:
        xCentres.append(0.5 * (xEdges[i] + xEdges[i - 1]))

    for i in range(len(yEdges))[1:]:
        yCentres.append(0.5 * (yEdges[i] + yEdges[i - 1]))

    return array, xCentres, yCentres

def gaussian2D((x, y), height, xMean, yMean, xSigma, ySigma, cor):
    '''Author: Jack Griffiths'''

    x = np.array(x).astype(np.float64)
    y = np.array(y).astype(np.float64)
    exponent = (((x - xMean) / xSigma) ** 2)
    exponent += (((y - yMean) / ySigma) ** 2)
    exponent -= (2. * cor * (x - xMean) * (y - yMean)) / (xSigma * ySigma)
    exponent /= (2 * (1 - (cor ** 2)))
    output = height * np.exp(-1. * exponent)

    return output

def fitGauss2D(array, xCentres, yCentres):
    '''Author: Jack Griffiths'''

    x,y,z=[],[],[]

    for i in range(len(yCentres)):
        for j in range(len(xCentres)):
            x.append(xCentres[j])
            y.append(yCentres[i])
            z.append(array[j][i])

    xMean = np.sum(np.array(x) * np.array(z)) / np.sum(np.array(z))
    xSigma =np.sum(abs(np.array(x) - xMean) * np.array(z)) / np.sum(np.array(z))
    yMean = np.sum(np.array(y) * np.array(z)) / np.sum(np.array(z))
    ySigma = np.sum(abs(np.array(y) -yMean) * np.array(z)) / np.sum(np.array(z))

    try:
        params = spo.curve_fit(gaussian2D, (x,y), z, [np.max(z), xMean, yMean, xSigma, ySigma, 0.])

    except RuntimeError:
        print 'Fit Failed!'

        return None

    params = [params[0], np.sqrt(np.diag(params[1]))]

    return params

def halfMaximumLine2D(fit, heightFraction, numberOfPoints, accuracy = 0.00000001):
    '''Author: Jack Griffiths'''

    radius = []
    theta = np.linspace(0, 2 * np.pi, numberOfPoints)

    cut = fit[0][0]*heightFraction

    for i in theta:
        r = 0.
        step=1.
        x = np.cos(i)
        y = np.sin(i)

        while step > accuracy:

            while gaussian2D(((x * r + fit[0][1]), (y * r + fit[0][2])), * fit[0]) > cut:
                r += step

            r -= step
            step *= 0.1

        radius.append(r)

    x=[]
    y=[]

    for i in range(len(radius)):
        x.append(radius[i]*np.cos(theta[i]))
        y.append(radius[i]*np.sin(theta[i]))

    x = np.array(x) + fit[0][1]
    y = np.array(y) + fit[0][2]

    return x, y

def containingRing(fit, xData, yData, fractionInside, numberOfPoints, accuracy = 0.00000001):
    '''Author: Jack Griffiths'''

    height = 1.
    step = 1.

    while step > accuracy:
        numberInside = 0.

        for i in range(len(xData)):
            h = gaussian2D((xData[i], yData[i]), * fit[0])

            if h >= height * fit[0][0]:
                numberInside += 1

        if numberInside/len(xData) < fractionInside:
            height -= step

        else:
            height += step
            step /= 10

    return halfMaximumLine2D(fit, height, numberOfPoints)

def plotIntensityRatios(outputFile, plot = True, xBins = 150, yBins = 120, ringFraction = 0.5, closeFigures = False):

    if plot == True:
        print '\nPlotting intensity ratios...'

    else:
        print '\n Gathering intensity ratios...'

    img = 'N/A'
    all_spectra = outputFile['Fitted spectra']

    cmPeakPositions = []
    intensityRatios = []

    spectra = sorted([spectrum for spectrum in all_spectra if spectrum[:8] == 'Spectrum'], key = lambda spectrum: int(spectrum[9:]))

    for spectrum in spectra:
        #print '\n', spectrum
        spectrum = all_spectra[spectrum]

        cmPeakPos = spectrum.attrs['Coupled mode wavelength']
        intensityRatio = spectrum.attrs['Intensity ratio']

        if spectrum.attrs['NPoM?'] == True and spectrum.attrs['Double Peak?'] == False and cmPeakPos != 'N/A' and cmPeakPos < 849 and intensityRatio != 'N/A':

            cmPeakPositions.append(cmPeakPos)
            intensityRatios.append(intensityRatio)

    if plot == True:

        try:

            y = np.array(intensityRatios)
            x = np.array(cmPeakPositions)

            yFilt = np.array([i for n, i in enumerate(y) if 0 < i < 10 and x[n] < 848])
            xFilt = np.array([x[n] for n, i in enumerate(y) if 0 < i < 10 and x[n] < 848])

            x = xFilt
            y = yFilt

            array, xCentres, yCentres = createDensityArray(x, y, xBins = xBins, yBins = yBins)
            fit2D = fitGauss2D(array, xCentres, yCentres)

            xMean = fit2D[0][1]
            yMean = fit2D[0][2]

            xRing, yRing = containingRing(fit2D, x, y, ringFraction, 10000)

            fig = plt.figure(figsize = (7, 7))

            plt.plot(xRing, yRing, 'k-', lw = 2)
            plt.plot([xMean], [yMean], 'ko', markersize = 10)
            plt.ylim(0, 8)
            plt.ylabel('Intensity Ratio', fontsize = 18)
            plt.yticks(fontsize = 15)
            plt.xlim(550, 900)
            plt.xlabel('Coupled Mode Resonance', fontsize = 18)
            plt.xticks(fontsize = 15)

            fig.tight_layout()
            fig.savefig('Intensity Ratios.png', bbox_inches = 'tight')

            if closeFigures == True:
                plt.close(fig)

            img = Image.open('Intensity Ratios.png')
            img = np.array(img)
            img = img.transpose((1, 0, 2))

            print 'Intensity ratios plotted'

        except Exception as e:

            if len(spectra) <= 100:
                print 'Data set too small. Intensity ratio plot failed'

            else:
                print 'Intensity ratio plot failed because %s' % str(e)

            img = 'N/A'

    else:
        img = 'N/A'
        print 'Intensity ratios gathered'

    return intensityRatios, cmPeakPositions, img

def visualiseIntensityRatios(outputFile):

    '''OutputFile = open h5py.File or nplab.datafile.DataFile object with read/write permission'''

    allSpectra = outputFile['Fitted spectra']

    for spectrum in sorted(allSpectra, key = lambda spectrum: int(spectrum[9:])):
        specNumber = int(spectrum[9:])
        spectrum = allSpectra[spectrum]
        #gFit = spectrum['Fit']
        intensityRatio = spectrum.attrs['Intensity ratio']

        if intensityRatio != 'N/A':
            y = spectrum['Raw/Raw data (normalised)'][()]
            x = spectrum['Raw/Raw data (normalised)'].attrs['wavelengths'][()]
            ySmooth = spectrum['Fit/Smoothed data'][()]
            xTrunc = spectrum['Fit/Smoothed data'].attrs['wavelengths']
            zeroLine = np.array([0] * len(xTrunc))
            transHeight = spectrum.attrs['Transverse mode intensity']
            transWl = spectrum.attrs['Transverse mode wavelength']
            cmHeight = spectrum.attrs['Coupled mode intensity']
            cmWl = spectrum.attrs['Coupled mode wavelength']
            xTransVert = np.array([transWl] * 10)
            yTransVert = np.linspace(transHeight, cmHeight, 10)
            xCmVert = np.array([cmWl] * 10)
            yCmVert = np.linspace(transHeight, cmHeight, 10)
            transHoriz = np.array([transHeight] * len(xTrunc))
            cmHoriz = np.array([cmHeight] * len(xTrunc))

            if 'Intensity ratio measurement' in spectrum:
                del spectrum['Intensity ratio measurement']

            gIrVis = spectrum.create_group('Intensity ratio measurement')

            dRaw = gIrVis.create_dataset('Raw', data = y)
            dRaw.attrs['wavelengths'] = x
            dSmooth = gIrVis.create_dataset('Smoothed', data = ySmooth)
            dSmooth.attrs['wavelengths'] = xTrunc
            dZero = gIrVis.create_dataset('Zero', data = zeroLine)
            dZero.attrs['wavelengths'] = dSmooth.attrs['wavelengths']
            dTransVert = gIrVis.create_dataset('Transverse mode position', data = yTransVert)
            dTransVert.attrs['wavelengths'] = xTransVert
            dCmVert = gIrVis.create_dataset('Coupled mode position', data = yCmVert)
            dCmVert.attrs['wavelengths'] = xCmVert
            dTransHoriz = gIrVis.create_dataset('Transverse mode height', data = transHoriz)
            dTransHoriz.attrs['wavelengths'] = xTrunc
            dCmHoriz = gIrVis.create_dataset('Coupled mode height', data = cmHoriz)
            dCmHoriz.attrs['wavelengths'] = xTrunc

            if '/All spectra/Spectra with peak heights/Spectrum %s' % specNumber in outputFile:
                del outputFile['All spectra/Spectra with peak heights/Spectrum %s' % specNumber]

            outputFile['All spectra/Spectra with peak heights/Spectrum %s' % specNumber] = gIrVis

def updateTransAndCoupledMode(outputFile, transGuess = 533, transRange = [500, 550], reNormalise = True):

    print '\nUpdating trans and coupled mode parameters'

    gSpectra = outputFile['Fitted spectra']

    allSpectra = sorted([spectrum for spectrum in outputFile['Fitted spectra']], key = lambda spectrum: int(spectrum[9:]))
    allSpectra = [spectrum for spectrum in allSpectra if gSpectra[spectrum].attrs['NPoM?'] == True]

    for spectrum in allSpectra:
        spectrum = gSpectra[spectrum]
        x = spectrum['Fit/Smoothed data'].attrs['wavelengths'][()]
        y_smooth = np.array(spectrum['Fit/Smoothed data'][()])
        fitComps = spectrum['Fit/Final components/']
        fitParams = {'g%s' % n : {key : fitComps[n].attrs[key] for key in fitComps[n].attrs.keys() if key != 'wavelengths'} for n in fitComps}

        tcMetadata = findTransAndCoupledMode(x, y_smooth, fitParams, transGuess = transGuess, transRange = transRange, plot = False)

        spectrum.attrs['Transverse mode intensity'] = tcMetadata['transverse_mode_intensity']
        spectrum.attrs['Transverse mode wavelength'] = tcMetadata['transverse_mode_position']
        spectrum.attrs['Coupled mode intensity'] = tcMetadata['coupled_mode_intensity']
        spectrum.attrs['Coupled mode wavelength'] = tcMetadata['coupled_mode_position']
        spectrum.attrs['Intensity ratio'] = tcMetadata['intensity_ratio']

        if reNormalise == True:

            transHeight = tcMetadata['transverse_mode_intensity']

            datasetsToUpdate = ['Fit/Best fit',
                                'Fit/Final components',
                                'Fit/Raw data (truncated, normalised)',
                                'Fit/Smoothed data',
                                'Raw/Raw data (normalised)']

            for dataset in datasetsToUpdate:

                if dataset == 'Fit/Final components':

                    for comp in spectrum[dataset]:
                        data = spectrum[dataset][comp] / transHeight
                        del spectrum[dataset][comp]
                        compDset = spectrum.create_dataset('%s/%s' % (dataset, comp), data = data)
                        compDset.attrs['wavelengths'] = x

                        '''May need to update component parameters also'''

                        for key in fitParams['g%s' % comp].keys():
                            compDset.attrs[key] = fitParams['g%s' % comp][key]

                else:
                    attrs = {key : spectrum[dataset].attrs[key] for key in spectrum[dataset].attrs.keys()}
                    data = spectrum[dataset][()] / transHeight
                    del spectrum[dataset]
                    dSet = spectrum.create_dataset(dataset, data = data)

                    for key in attrs:
                        dSet.attrs[key] = attrs[key]

    print 'Transverse and coupled mode updated'

def plotInitStack(x, yData, imgName = 'Initial Stack', closeFigures = False):

    yDataTrunc = [truncateSpectrum(wavelengths, spectrum)[1] for spectrum in yData]
    xTrunc = truncateSpectrum(x, yData[0])[0]

    transIndex = np.where(xTrunc == 533)[0][0]
    yDataTrunc = np.array([spectrum / spectrum[transIndex] for spectrum in yDataTrunc])

    xStack = xTrunc
    yStack = range(len(yDataTrunc))
    zStack = np.vstack(yDataTrunc)

    fig = plt.figure(figsize = (9, 7))

    plt.pcolormesh(xStack, yStack, zStack, cmap = 'inferno', vmin = 0, vmax = 4)
    plt.xlim(450, 900)
    plt.xlabel('Wavelength (nm)', fontsize = 14)
    plt.ylabel('Spectrum #', fontsize = 14)
    cbar = plt.colorbar()
    cbar.set_ticks([])
    cbar.set_label('Intensity (a.u.)', fontsize = 14)
    plt.ylim(min(yStack), max(yStack))
    plt.yticks(fontsize = 14)
    plt.xticks(fontsize = 14)

    if imgName.endswith('.png'):
        plt.title(imgName[:-4])

    else:
        plt.title(imgName)
        imgName = '%s.png' % imgName

    fig.savefig(imgName, bbox_inches = 'tight')

    if closeFigures == True:
        plt.close(fig)

    img = np.array(Image.open(imgName)).transpose((1, 0, 2))

    #except Exception as e:
    #    print 'Plotting of %s failed because %s' % (imgName, str(e))
    #    img = 'N/A'

    return img

def plotStackedMap(spectraSorted, imgName = 'Stack', closeFigures = False):

    try:
        yDataRaw = [spectrum['Raw/Raw data (normalised)'][()] for spectrum in spectraSorted]
        yDataRaw = np.array([spectrum for spectrum in yDataRaw if type(spectrum) != str])

        n = 0
        wavelengths = spectraSorted[n]['Raw/Raw data (normalised)'].attrs['wavelengths']

        while type(wavelengths) == str:
            n += 1
            wavelengths = spectraSorted[n]['Raw/Raw data (normalised)'].attrs['wavelengths']

        yDataTrunc = np.array([truncateSpectrum(wavelengths, spectrum)[1] for spectrum in yDataRaw])
        wavelengthsTrunc = truncateSpectrum(wavelengths, yDataRaw[0])[0]

        xStack = wavelengthsTrunc
        yStack = range(len(yDataTrunc))
        zStack = np.vstack(yDataTrunc)

        fig = plt.figure(figsize = (9, 7))

        plt.pcolormesh(xStack, yStack, zStack, cmap = 'inferno', vmin = 0, vmax = 4)
        plt.xlim(450, 900)
        plt.xlabel('Wavelength (nm)', fontsize = 14)
        plt.ylabel('Spectrum #', fontsize = 14)
        cbar = plt.colorbar()
        cbar.set_ticks([])
        cbar.set_label('Intensity (a.u.)', fontsize = 14)
        plt.ylim(min(yStack), max(yStack))
        plt.yticks(fontsize = 14)
        plt.xticks(fontsize = 14)

        if imgName.endswith('.png'):
            plt.title(imgName[:-4])

        else:
            plt.title(imgName)
            imgName = '%s.png' % imgName

        fig.savefig(imgName, bbox_inches = 'tight')

        if closeFigures == True:
            plt.close(fig)

        img = np.array(Image.open(imgName)).transpose((1, 0, 2))

    except Exception as e:
        print 'Plotting of %s failed because %s' % (imgName, str(e))
        img = 'N/A'

    return img

def plotAllStacks(outputFile, closeFigures = False):

    print '\nPlotting stacked spectral maps...'

    gSpectra = outputFile['Fitted spectra']
    gStackOutput = outputFile.create_group('Statistics/Stacks')

    '''By order of measurement'''

    spectra = [spectrum for spectrum in gSpectra if spectrum[:8] == 'Spectrum']
    spectraSorted = sorted(spectra, key = lambda spectrum: int(spectrum[9:]))
    spectraSorted = [gSpectra[spectrum] for spectrum in spectraSorted]

    gStackOutput.create_dataset('All',
                                data = plotStackedMap(spectraSorted, imgName = 'Stack (all)', closeFigures = closeFigures))

    '''By CM wavelength'''

    cmWlName = 'Coupled mode wavelength'
    spectra = [gSpectra[spectrum] for spectrum in gSpectra if spectrum[:8] == 'Spectrum' and
               gSpectra[spectrum].attrs[cmWlName] != 'N/A']
    spectraSorted = sorted(spectra, key = lambda spectrum: spectrum.attrs[cmWlName])

    gStackOutput.create_dataset('By C mode',
                                data = plotStackedMap(spectraSorted, imgName = 'Stack (CM wavelength)', closeFigures = closeFigures))

    '''By TM wavelength'''

    tmWlName = 'Transverse mode wavelength'

    try:
        spectra = [gSpectra[spectrum] for spectrum in gSpectra if spectrum[:8] == 'Spectrum' and
               gSpectra[spectrum].attrs[tmWlName] != 'N/A']

    except:
        tmWlName = 'Transverse mode wavelength)'
        spectra = [gSpectra[spectrum] for spectrum in gSpectra if spectrum[:8] == 'Spectrum' and
               gSpectra[spectrum].attrs[tmWlName] != 'N/A']

    spectraSorted = sorted(spectra, key = lambda spectrum: spectrum.attrs[tmWlName])

    gStackOutput.create_dataset('By T mode',
                                data = plotStackedMap(spectraSorted, imgName = 'Stack (TM wavelength)', closeFigures = closeFigures))

    '''By intensity ratio'''

    irName = 'Intensity ratio'

    spectra = [gSpectra[spectrum] for spectrum in gSpectra if spectrum[:8] == 'Spectrum' and
               gSpectra[spectrum].attrs[irName] != 'N/A']
    spectraSorted = sorted(spectra, key = lambda spectrum: spectrum.attrs[irName])

    gStackOutput.create_dataset('By intensity ratio',
                                data = plotStackedMap(spectraSorted, imgName = 'Stack (intensity ratio)', closeFigures = closeFigures))

    '''Doubles in order of measurement'''

    spectra = [spectrum for spectrum in gSpectra if spectrum[:8] == 'Spectrum' and
               gSpectra[spectrum].attrs['Double Peak?'] == True]

    if len(spectra) > 0:

        spectraSorted = sorted(spectra, key = lambda spectrum: int(spectrum[9:]))
        spectraSorted = [gSpectra[spectrum] for spectrum in spectraSorted]

        '''By order of measurement'''

        gStackOutput.create_dataset('All doubles',
                                    data = plotStackedMap(spectraSorted, imgName = 'Stack (all doubles)', closeFigures = closeFigures))

        '''Doubles by CM wavelength'''

        cmWlName = 'Coupled mode wavelength'
        spectra = [gSpectra[spectrum] for spectrum in gSpectra if spectrum[:8] == 'Spectrum' and
                   gSpectra[spectrum].attrs[cmWlName] != 'N/A' and gSpectra[spectrum].attrs['Double Peak?'] == True]
        spectraSorted = sorted(spectra, key = lambda spectrum: spectrum.attrs[cmWlName])

        gStackOutput.create_dataset('Doubles by C mode',
                                    data = plotStackedMap(spectraSorted, imgName = 'Stack (Doubles by CM wavelength)', closeFigures = closeFigures))

        '''Doubles by TM wavelength'''

        tmWlName = 'Transverse mode wavelength'

        try:
            spectra = [gSpectra[spectrum] for spectrum in gSpectra if spectrum[:8] == 'Spectrum' and
                   gSpectra[spectrum].attrs[tmWlName] != 'N/A' and gSpectra[spectrum].attrs['Double Peak?'] == True]

        except:
            tmWlName = 'Transverse mode wavelength)'

        spectraSorted = sorted(spectra, key = lambda spectrum: spectrum.attrs[tmWlName])

        gStackOutput.create_dataset('Doubles by T mode',
                                    data = plotStackedMap(spectraSorted, imgName = 'Stack (Doubles by TM wavelength)', closeFigures = closeFigures))

        '''Doubles by intensity ratio'''

        irName = 'Intensity ratio'

        spectra = [gSpectra[spectrum] for spectrum in gSpectra if spectrum[:8] == 'Spectrum' and
                   gSpectra[spectrum].attrs[irName] != 'N/A' and gSpectra[spectrum].attrs['Double Peak?'] == True]
        spectraSorted = sorted(spectra, key = lambda spectrum: spectrum.attrs[irName])

        gStackOutput.create_dataset('Doubles by intensity ratio',
                                    data = plotStackedMap(spectraSorted, imgName = 'Stack (Doubles by intensity ratio)', closeFigures = closeFigures))

    else:
        print 'No doubles to plot'

    print 'Stacks plotted'

def doStats(outputFile, minBinFactor = 5, stacks = True, hist = True, intensityRatios = True, closeFigures = False):

    if 'Statistics' in outputFile:
        del outputFile['Statistics']

    if stacks == True:
        plotAllStacks(outputFile, closeFigures = closeFigures)

    if hist == True:
        frequencies, bins, yDataBinned, histImg = plotHistogram(outputFile, minBinFactor = minBinFactor, closeFigures = closeFigures)

        avg_resonance, stderr, fwhm = histyFit(frequencies, bins)

        gHist = outputFile.create_group('Statistics/Histogram/')
        gHist.attrs['Average resonance'] = avg_resonance
        gHist.attrs['Error'] = stderr
        gHist.attrs['FWHM'] = fwhm

        dBins = gHist.create_dataset('Bins', data = bins)
        dFreq = gHist.create_dataset('Frequencies', data = frequencies)
        dFreq.attrs['wavelengths'] = dBins
        gHist.create_dataset('Histogram', data = histImg)
        gYDataBinned = gHist.create_group('Binned y data/')

        for n, yDatum in enumerate(yDataBinned):
            gYDataBinned.create_dataset('Bin %s data, peakpos = %s' % (n, bins[n]), data = yDatum)

    if intensityRatios == True:

        numberOfSpectra = len(outputFile['Fitted spectra'])
        xBins = numberOfSpectra / 12
        yBins = numberOfSpectra / 12

        intensityRatios, cmPeakPositions, irImg = plotIntensityRatios(outputFile, plot = True, xBins = xBins, yBins = yBins, closeFigures = closeFigures)

        outputFile['Statistics/Intensity ratios'] = irImg
        d_ir = outputFile['Statistics/Intensity ratios']
        d_ir.attrs['Intensity ratios'] = intensityRatios
        d_ir.attrs['Peak positions'] = cmPeakPositions

        visualiseIntensityRatios(outputFile)

def fitAllSpectra(x, yData, outputFile, startSpec = 0, monitor_progress = False, plot = False, raiseExceptions = False, closeFigures = False):

    absolute_start_time = time.time()

    '''Fits all spectra and populates h5 file with relevant output data. h5 file must be opened before the function and closed afterwards'''

    print '\nBeginning fit procedure...'

    if len(yData) > 2500:
        print 'About to fit %s spectra. This may take a while...' % len(yData)

    '''SPECIFY INITIAL FIT PARAMETERS HERE'''

    doubles_threshold = 0.4
    detection_threshold = 0
    doubles_dist = 50

    fitted_spectra = []
    failed_spectra = []
    failed_spectra_indices = []

    nummers = range(5, 101, 5)

    total_fit_start = time.time()
    print '\n0% complete'

    g_all = outputFile.create_group('Fitted spectra/')
    g_spectra_only = outputFile.create_group('All spectra/Spectra')

    for n, y in enumerate(yData[:]):

        nn = n
        n += startSpec

        if monitor_progress in [True, 'main']:
            print 'Spectrum %s' % n

        if int(100 * nn / len(yData[:])) in nummers:
            current_time = time.time() - total_fit_start
            mins = int(current_time / 60)
            secs = (np.round((current_time % 60)*100))/100
            print '%s%% (%s spectra) complete in %s min %s sec' % (nummers[0], nn, mins, secs)
            nummers = nummers[1:]

        if raiseExceptions == False:

            try:
                fitted_spectrum = fitNpomSpectrum(x, y, detection_threshold = detection_threshold, doubles_threshold = doubles_threshold,
                                                  doubles_dist = doubles_dist, monitor_progress = monitor_progress, plot = plot)
                fitted_spectra.append(fitted_spectrum)
                fitError = 'N/A'

            except Exception as e:
                #raise e
                fitted_spectrum = DF_Spectrum(y, 'N/A', False, 'N/A', 'N/A', 'N/A')
                fitted_spectrum = fitted_spectrum.metadata
                failed_spectra.append(fitted_spectrum)
                failed_spectra_indices.append(n)
                fitError = e

                print 'Spectrum %s failed because: \n\t"%s"' % (n, e)

        elif raiseExceptions == True:
            fitted_spectrum = fitNpomSpectrum(x, y, detection_threshold = detection_threshold, doubles_threshold = doubles_threshold,
                                              doubles_dist = doubles_dist, monitor_progress = monitor_progress, plot = plot)
            fitted_spectra.append(fitted_spectrum)
            fitError = 'N/A'

        '''Adds data to open HDF5 file'''

        g = g_all.create_group('Spectrum %s/' % n)

        if fitted_spectrum['NPoM?'] == True:
            raw_data = fitted_spectrum['raw_data']
            norm_data = fitted_spectrum['truncated_spectrum']
            trunc_wl = fitted_spectrum['truncated_wavelengths']

        else:
            raw_data = y
            norm_index = np.where(np.round(x) - 533 < 0.5)[0][0]
            norm_data = raw_data/raw_data[norm_index]
            norm_data = truncateSpectrum(x, norm_data)
            trunc_wl = norm_data[0]
            norm_data = norm_data[1]

        main_norm_spec = g_spectra_only.create_dataset('Spectrum %s' % n, data = norm_data)
        main_norm_spec.attrs['wavelengths'] = trunc_wl

        if fitError != 'N/A':
            main_norm_spec.attrs['Fitting error'] = str(fitError)

        g.attrs['NPoM?'] = fitted_spectrum['NPoM?']
        g.attrs['Double Peak?'] = fitted_spectrum['double_peak?']
        g.attrs['Transverse mode intensity'] = fitted_spectrum['transverse_mode_intensity']
        g.attrs['Transverse mode wavelength'] = fitted_spectrum['transverse_mode_position']
        g.attrs['Coupled mode intensity'] = fitted_spectrum['coupled_mode_intensity']
        g.attrs['Coupled mode wavelength'] = fitted_spectrum['coupled_mode_position']
        g.attrs['Intensity ratio'] = fitted_spectrum['intensity_ratio']
        g.attrs['Error(s)'] = str(fitError)

        g_raw = g.create_group('Raw/')

        d_raw = g_raw.create_dataset('Raw data', data = raw_data)
        d_raw.attrs['wavelengths'] = fitted_spectrum['full_wavelengths']

        d_raw_norm = g_raw.create_dataset('Raw data (normalised)', data = fitted_spectrum['normalised_spectrum'])
        d_raw_norm.attrs['wavelengths'] = d_raw.attrs['wavelengths']

        g_fit = g.create_group('Fit/')

        d_raw_trunc = g_fit.create_dataset('Raw data (truncated, normalised)', data = fitted_spectrum['truncated_spectrum'])
        d_raw_trunc.attrs['wavelengths'] = main_norm_spec.attrs['wavelengths']

        d_smooth = g_fit.create_dataset('Smoothed data', data = fitted_spectrum['smoothed_spectrum'])
        d_smooth.attrs['wavelengths'] = d_raw_trunc.attrs['wavelengths']
        d_smooth.attrs['second_derivative'] = fitted_spectrum['second_derivative']

        d_best_fit = g_fit.create_dataset('Best fit', data = fitted_spectrum['best_fit'])
        d_best_fit.attrs['wavelengths'] = d_raw_trunc.attrs['wavelengths']
        d_best_fit.attrs['Initial guess'] = fitted_spectrum['initial_guess']
        d_best_fit.attrs['Residuals'] = fitted_spectrum['residuals']

        g_comps = g_fit.create_group('Final components/')

        comps = fitted_spectrum['final_components']

        if comps != 'N/A':

            for i in range(len(comps.keys())):
                component = g_comps.create_dataset(str(i), data = comps['g%s_' % i])
                component_params = fitted_spectrum['final_params']['g%s' % i]
                component.attrs['center'] = component_params['center']
                component.attrs['height'] = component_params['height']
                component.attrs['amplitude'] = component_params['amplitude']
                component.attrs['sigma'] = component_params['sigma']
                component.attrs['fwhm'] = component_params['fwhm']

    g_all.attrs['Failed spectra indices'] = failed_spectra_indices

    print '100% complete'
    total_fit_end = time.time()
    time_elapsed = total_fit_end - total_fit_start

    mins = int(time_elapsed / 60)
    secs = int(np.round(time_elapsed % 60))

    print '\n%s spectra fitted in %s min %s sec' % (nn + 1, mins, secs)

    doStats(outputFile, closeFigures = closeFigures)

    absolute_end_time = time.time()
    time_elapsed = absolute_end_time - absolute_start_time

    mins = int(time_elapsed / 60)
    secs = int(np.round(time_elapsed % 60))

    printEnd()

    if len(failed_spectra) == 0:
        print '\nFinished in %s min %s sec. Smooth sailing.' % (mins, secs)

    elif len(failed_spectra) == 1:
        print '\nPhew... finished in %s min %s sec with only %s failure' % (mins, secs, len(failed_spectra))

    elif len(failed_spectra) > len(fitted_spectra):
        print '\nHmmm... finished in %s min %s sec but with %s failures and only %s successful fits' % (mins, secs, len(failed_spectra), len(fitted_spectra))

    elif mins > 30:
        print '\nM8 that took ages. %s min %s sec' % (mins, secs)

    else:
        print '\nPhew... finished in %s min %s sec with only %s failures' % (mins, secs, len(failed_spectra))

    print ''

if __name__ == '__main__':
    print 'Functions initialised'

    statsOnly = False

    if statsOnly == False:

        print '\nRetrieving data...'

        startSpec = 0
        finishSpec = 0

        spectra, wavelengths, background, reference = retrieveData('summary', startSpec, finishSpec)
        x, yData = prepareData(spectra, wavelengths, reference)
        initImg = plotInitStack(x, yData, imgName = 'Initial Stack', closeFigures = False)

        outputFile = createOutputFile('MultiPeakFitOutput')

        with h5py.File(outputFile, 'a') as f:
            fitAllSpectra(x, yData, f, startSpec = startSpec, raiseExceptions = True)

    elif statsOnly == True:
        outputFile = 'MultiPeakFitOutputComplete.h5'

        with h5py.File(outputFile, 'a') as f:
            doStats(f, minBinFactor = 6, stacks = False, hist = True, intensityRatios = False, closeFigures = True)