#! /usr/bin/env python3
# Licensed under a GPLv3 style license - see LICENSE

import numpy as np
import os.path
import sys
from datetime import datetime
from astropy.io import fits
from astropy.time import Time
from astropy.coordinates import SkyCoord, EarthLocation
import astropy.units as u
from astropy.constants import c

from .readmultispec import readmultispec
from .airtovac import airtovac

from .FTS_resample import resample, FTSfits

try:
    # check if PyCPL is available
    import cpl
    from cpl.core import Table
    from cpl.core import PropertyList, Property
    pycpl = 1
    print('Using PyCPL for data reading and writing.')
except:
    pycpl = 0
    print('No PyCPL version has been found. Using astropy for data reading and writing.')

# see https://github.com/mzechmeister/serval/blob/master/src/inst_FIES.py

path = os.path.join(os.path.dirname(__file__), '..') + "/lib/CRIRES/"

location = crires = EarthLocation.from_geodetic(
    lat=-24.6268 * u.deg, lon=-70.4045 * u.deg, height=2648 * u.m
)

oset = '1:19'

ip_guess = {'s': 1.5}

def Spectrum(filename='', order=None, targ=None):

    order_drs, detector = divmod(order-1, 3)
    order_drs = 7 - order_drs	# order number (CRIRES+ definition)
    detector += 1			# detector number (1,2,3)
    
    exptime = 0

    if pycpl:
        hdr = PropertyList.load(filename, 0)    
        ra = hdr["RA"].value
        de = hdr["DEC"].value
        setting = hdr["ESO INS WLEN ID"].value
        nod_type = hdr["ESO PRO CATG"].value
        cal = PropertyList.load_regexp(filename, 0, "ESO PRO REC1 CAL", False)
        
        try:
            # midtime; for data reduced with new DRS pipeline version
            # ensure input spectra is a combined spectrum (nodA+nodB)
            # non-combined nodA and nodB spectra have the same time stamp
            # bug in the current DRS pipeline versions
            if str(nod_type) != 'OBS_NODDING_EXTRACT_COMB': raise
            dateobs = Time(hdr["ESO DRS TMID"].value, format='mjd').isot
        except:
            dateobs = hdr["DATE-OBS"].value
            ndit = hdr["ESO DET NDIT"].value
            nods = hdr["ESO PRO DATANCOM"].value   # Number of combined frames
            if str(nod_type) in ('OBS_NODDING_EXTRACTA', 'OBS_NODDING_EXTRACTB'):
                # just half of the nods are combined
                nods /= 2
            exptime = hdr["ESO DET SEQ1 DIT"].value
            exptime = (exptime*nods*ndit) / 2.0           

        tbl = Table.load(filename, detector)
        spec = np.array(tbl["0"+str(order_drs)+"_01_SPEC"])
        err = np.array(tbl["0"+str(order_drs)+"_01_ERR"])

    else:
        hdu = fits.open(filename, ignore_blank=True)
        hdr = hdu[0].header
        ra = hdr.get('RA', np.nan)
        de = hdr.get('DEC', np.nan)
        setting = hdr['ESO INS WLEN ID']
        nod_type = hdr['ESO PRO CATG']
        cal = hdr['ESO PRO REC1 CAL* CATG']
        
        try:
            if str(nod_type) != 'OBS_NODDING_EXTRACT_COMB': raise
            dateobs = Time(hdr["ESO DRS TMID"], format='mjd').isot
        except:            
            dateobs = hdr['DATE-OBS']
            ndit = hdr.get('ESO DET NDIT', 1)
            nods = hdr.get('ESO PRO DATANCOM', 1)   # Number of combined frames 
            if str(nod_type) in ('OBS_NODDING_EXTRACTA', 'OBS_NODDING_EXTRACTB'):
                # just half of the nods are combined
                nods /= 2
            exptime = hdr.get('ESO DET SEQ1 DIT', 0)
            exptime = (exptime*nods*ndit) / 2.0

        err = hdu[detector].data["0"+str(order_drs)+"_01_ERR"]
        spec = hdu[detector].data["0"+str(order_drs)+"_01_SPEC"]

    pixel = np.arange(spec.size)

    targdrs = SkyCoord(ra=ra*u.deg, dec=de*u.deg)
    if not targ: targ = targdrs
    midtime = Time(dateobs, format='isot', scale='utc') + exptime * u.s
    berv = targ.radial_velocity_correction(obstime=midtime, location=crires)
    berv = berv.to(u.km/u.s).value
    bjd = midtime.tdb
   
    # currently running tests with wavesolution from DRS pipeline
    # DRS is giving better results for some orders
    # this may can be removed in the near future
    if 0: #str(setting) in ('K2148', 'K2166', 'K2192'):
	    # using an own wavelength solution instead of the one created by DRS
        file_wls = np.genfromtxt(path+'wavesolution_own/wave_solution_'+str(setting)+'.dat', dtype=None, names=True).view(np.recarray)
        coeff_wls = [file_wls.b1[order-1], file_wls.b2[order-1], file_wls.b3[order-1]]
        wave = np.poly1d(coeff_wls[::-1])(pixel)

    else:
        if pycpl:
            wave = np.array(tbl["0"+str(order_drs)+"_01_WL"]) *10
        else:
            wave = (hdu[detector].data["0"+str(order_drs)+"_01_WL"]) * 10
            
    if 'CAL_FLAT_EXTRACT_1D' not in str(cal):
        # check if data are already blaze corrected by DRS pipeline
        # otherwise use own blaze correction generated from 1D FLAT spectra 
        # not yet tested for all settings
        hdu = fits.open(path+'blaze_own.fits', ignore_blank=True)       
        blaze = hdu[setting].data["0"+str(order_drs)+"_0"+str(detector)+"_BLAZE"]        
        spec /= blaze

    flag_pixel = 1 * np.isnan(spec)		# bad pixel map

    return pixel, wave, spec, err, flag_pixel, bjd, berv


def Tpl(tplname, order=None, targ=None):
    '''Tpl should return barycentric corrected wavelengths'''

    if tplname.endswith('_tpl.fits'):
        # tpl created with viper
        
        order_drs, detector = divmod(order-1, 3)
        order_drs = 7 - order_drs		# order number (CRIRES+ definition)
        detector += 1			# detector number (1,2,3)

        if pycpl:
            hdr = PropertyList.load(tplname, 1)
            tbl = Table.load(tplname, detector)
            spec = np.array(tbl["0"+str(order_drs)+"_01_SPEC"])
            err = np.array(tbl["0"+str(order_drs)+"_01_ERR"])
            wave = np.array(tbl["0"+str(order_drs)+"_01_WL"])
        else:
            hdu = fits.open(tplname, ignore_blank=True)
            hdr = hdu[0].header    
            err = hdu[detector].data["0"+str(order_drs)+"_01_ERR"]
            spec = hdu[detector].data["0"+str(order_drs)+"_01_SPEC"]
            wave = hdu[detector].data["0"+str(order_drs)+"_01_WL"]
            pixel = np.arange(spec.size)
    else:
        pixel, wave, spec, err, flag_pixel, bjd, berv = Spectrum(tplname, order=order, targ=targ)
        wave *= 1 + (berv*u.km/u.s/c).to_value('')

    return wave, spec


def FTS(ftsname='lib/CRIRES/FTS/CRp_SGC2_FTStmpl-HR0p007-WN3000-5000_Kband.dat', dv=100):

    return resample(*FTSfits(ftsname), dv=dv)


def write_fits(wtpl_all, tpl_all, e_all, list_files, file_out):
    if pycpl:
        write_fits_cpl(wtpl_all, tpl_all, e_all, list_files, file_out)
    else:
        write_fits_nocpl(wtpl_all, tpl_all, e_all, list_files, file_out)


def write_fits_cpl(wtpl_all, tpl_all, e_all, list_files, file_out):

    file_in = list_files[0]

    # copy header from first fits file
    hdr = PropertyList.load(file_in, 0)

    if len(list_files) > 1:
        # delete parts that vary for all observations
        PropertyList.del_regexp(hdr, "DATE-OBS", False)
        PropertyList.del_regexp(hdr, "UTC", False)
        PropertyList.del_regexp(hdr, "LST", False)
        PropertyList.del_regexp(hdr, "ARCFILE", False)
        PropertyList.del_regexp(hdr, "ESO INS SENS*", False)
        PropertyList.del_regexp(hdr, "ESO INS TEMP*", False)
        PropertyList.del_regexp(hdr, "ESO INS1*", False)
        PropertyList.del_regexp(hdr, "ESO DET*", False)
        PropertyList.del_regexp(hdr, "ESO OBS*", False)
        PropertyList.del_regexp(hdr, "ESO TPL*", False)
        PropertyList.del_regexp(hdr, "ESO TEL*", False)
        PropertyList.del_regexp(hdr, "ESO OCS MTRLGY*", False)
        PropertyList.del_regexp(hdr, "ESO ADA*", False)
        PropertyList.del_regexp(hdr, "ESO AOS*", False)
        PropertyList.del_regexp(hdr, "ESO SEQ*", False)
        PropertyList.del_regexp(hdr, "ESO PRO DATANCOM", False)
        PropertyList.del_regexp(hdr, "ESO PRO REC1 PARAM*", False)
        PropertyList.del_regexp(hdr, "ESO PRO REC1 RAW*", False)

    # save raw file informations in FITS header    
    hdr.append(Property('HIERARCH ESO PRO REC2 ID', 'viper_create_tpl', 'Pipeline recipe'))

    for i in range(0, len(list_files), 1):
        pathi, filei = os.path.split(list_files[len(list_files)-i-1])
        hdr.append(Property('HIERARCH ESO PRO REC2 RAW'+str(len(list_files)-i)+' NAME', filei, 'File name'))

    hdr.append(Property('HIERARCH ESO PRO DATANCOM2', len(list_files), 'Number of combined frames'))

    for detector in (1, 2, 3):
        # data spread over 3 detectors, each having 6 orders

        # Update headers of the single detectors
        hdro = PropertyList.load(file_in, detector)
        hdro["EXPTIME"].value = 0
        PropertyList.del_regexp(hdro, "ESO *", False)

        tbl = Table.load(file_in, detector)   
        cols = tbl.column_names

        for cc in cols[::3]:
            odrs = int(cc.split('_')[0])  
            o = (7-odrs)*3 + detector
            if o in list(tpl_all.keys()):
                tbl["0"+str(odrs)+"_01_WL"] = wtpl_all[o]		# wavelength	
                tbl["0"+str(odrs)+"_01_SPEC"] = tpl_all[o]		# data
                tbl["0"+str(odrs)+"_01_ERR"] = e_all[o]			# errors
            else:
               # writing ones for non processed orders
                wave0 = np.array(tbl["0"+str(odrs)+"_01_WL"])
                tbl["0"+str(odrs)+"_01_WL"] = wave0 * 10
                tbl["0"+str(odrs)+"_01_SPEC"] = np.ones(2048)
                tbl["0"+str(odrs)+"_01_ERR"] = np.nan * np.ones(2048)

        if detector == 1:
            Table.save(tbl, hdr, hdro, file_out+'_tpl.fits', cpl.core.io.CREATE)
        else:     
            Table.save(tbl, None, hdro, file_out+'_tpl.fits', cpl.core.io.EXTEND)  


def write_fits_nocpl(wtpl_all, tpl_all, e_all, list_files, file_out):

    file_in = list_files[0]

    # copy header from first fits file
    hdu = fits.open(file_in, ignore_blank=True)
    hdr = hdu[0].header

    if len(list_files) > 1:
        # delete parts that vary for all observations
        del hdr['DATE-OBS']
        del hdr['UTC']
        del hdr['LST']
        del hdr['ARCFILE']
        del hdr['ESO INS SENS*']
        del hdr['ESO INS TEMP*']
        del hdr['ESO INS1*']
        del hdr['ESO DET*']
        del hdr['ESO OBS*']
        del hdr['ESO TPL*']
        del hdr['ESO TEL*']
        del hdr['ESO OCS MTRLGY*']
        del hdr['ESO ADA*']
        del hdr['ESO AOS*']
        del hdr['ESO SEQ*']
        del hdr['ESO PRO DATANCOM']
        del hdr['ESO PRO REC1 PARAM*']
        del hdr['ESO PRO REC1 RAW*']

        for hdri in hdu:
            hdri.header['EXPTIME'] = 0

    # file creation date
    now = datetime.now()
    dt_string = now.strftime("%Y-%m-%dT%H:%M:%S")
    hdr['DATE'] = dt_string

    # save raw file informations in FITS header
    hdr.set('HIERARCH ESO PRO REC2 ID', 'viper_create_tpl', 'Pipeline recipe', after='ESO PRO REC1 PIPE ID')

    for i in range(0, len(list_files), 1):
        pathi, filei = os.path.split(list_files[len(list_files)-i-1])
        hdr.set('HIERARCH ESO PRO REC2 RAW'+str(len(list_files)-i)+' NAME', filei, 'File name', after='ESO PRO REC2 ID')

    hdr.set('HIERARCH ESO PRO DATANCOM2', len(list_files), 'Number of combined frames', after='ESO PRO REC2 RAW'+str(len(list_files))+' NAME')

    # write the template data to the file            
    for detector in (1, 2, 3): 
        data = hdu[detector].data    
        cols = hdu[detector].columns   

        for cc in cols[::3]:
            odrs = int(cc.name.split('_')[0])    
            o = (7-odrs)*3 + detector
            if o in list(tpl_all.keys()):     
                data["0"+str(odrs)+"_01_WL"] = wtpl_all[o]		# wavelength	
                data["0"+str(odrs)+"_01_SPEC"] = tpl_all[o]		# data
                data["0"+str(odrs)+"_01_ERR"] = e_all[o]		# errors   
            else:
               # writing ones for non processed orders
                wave0 = data["0"+str(odrs)+"_01_WL"] 
                data["0"+str(odrs)+"_01_WL"] = wave0 * 10    # [Angstrom]
                data["0"+str(odrs)+"_01_SPEC"] = np.ones(2048)
                data["0"+str(odrs)+"_01_ERR"] = np.nan * np.ones(2048)
            
    hdu.writeto(file_out+'_tpl.fits', overwrite=True)
    hdu.close()
