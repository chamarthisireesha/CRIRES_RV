#! /usr/bin/env python3

# ./viper.py data/TLS/betgem/BETA_GEM.fits data/TLS/betgem/pepsib.20150409.000.sxt.awl.all6
# ./viper.py data/TLS/hd189733/TV00001.fits data/TLS/Deconv/HD189733.model
# ./viper.py data/TLS/hd189733/TV00001.fits data/TLS/Deconv/HARPS.2006-09-08T02\:12\:38.604_s1d_A.fits

import argparse

import numpy as np
from scipy import interpolate
from scipy.optimize import curve_fit
from astropy.io import fits
import vpr

from gplot import *
gplot.tmp = '$'
from pause import pause

from inst.inst_TLS import Spectrum, Tpl, FTS
from model import model, IP, show_model

c = 3e5   # [km/s] speed of light


o = 18; lmin = 5240; lmax = 5390

dirname = r''
v0 = -2
ftsname = dirname + 'lib/TLS/FTS/TLS_I2_FTS.fits'
obsname = dirname + 'data/TLS/betgem/BETA_GEM.fits'
tplname = dirname + 'data/TLS/betgem/pepsib.20150409.000.sxt.awl.all6'
obsname = dirname + 'data/TLS/hd189733/TV00001.fits'
tplname = dirname + 'data/TLS/Deconv/HD189733.model'
tplname = dirname + 'data/TLS/Deconv/HARPS.2006-09-08T02:12:38.604_s1d_A.fits'; v = -16.

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='VIPER - velocity and IP Estimator', add_help=False, formatter_class=argparse.RawTextHelpFormatter)
    argopt = parser.add_argument   # function short cut
    argopt('obsname', help='Filename of observation', default='data/TLS/betgem/BETA_GEM.fits', type=str)
    argopt('tpl', help='Filename of template', default='data/TLS/betgem/pepsib.20150409.000.sxt.awl.all6', type=str)
    argopt('-o', help='index for order', default=18, type=int)

    args = parser.parse_args()
    globals().update(vars(args))

####  FTS  ####

# using the supersampled log(wavelength) space with knot index j

w_I2, f_I2, xj_full, iod_j_full = FTS()

orders = np.arange(18,30)
rv = np.empty_like(orders*1.)
e_rv = np.empty_like(orders*1.)


def fit_chunk(o):
    ####  data TLS  ####
    w_i, f_i = Spectrum(obsname, o=o)
    i = np.arange(f_i.size)

    ####  stellar template  ####
    w_tpl, f_tpl = Tpl(tplname, o=o)

    lmin = max(w_tpl[0], w_i[0], w_I2[0])
    lmax = min(w_tpl[-1], w_i[-1], w_I2[-1])

    # display
    # pre-look raw input
    s = slice(*np.searchsorted(w_I2, [lmin, lmax]))
    s_s = slice(*np.searchsorted(w_tpl, [lmin, lmax]))

    if 0:
        gplot(w_I2[s], f_I2[s], 'w l lc 9,', w_tpl[s_s], f_tpl[s_s], 'w l lc 3,', w_i, f_i, 'w lp lc 1 pt 7 ps 0.5')
        #gplot(w_I2[s], f_I2[s]/1.18, 'w l lc 9,', w_tpl[s_s]*(1+12/c), f_tpl[s_s], 'w l lc 3,', w_i, f_i/1.04, 'w lp lc 1 pt 7 ps 0.5')

    # prepare input; convert discrete data to model

    # using the supersampled log(wavelength) space with knot index j

    sj = slice(*np.searchsorted(xj_full, [np.log(lmin)+100/c, np.log(lmax)-100/c])) # reduce range by 100 km/s
	
    xj = xj_full[sj]  
    iod_j = iod_j_full[sj]


    # convert discrete template into a function
    S_star = interpolate.interp1d(np.log(w_tpl), f_tpl)


    # setup the model
    S_mod = model(S_star, xj, iod_j, IP)

    # plot the IP
    gplot(S_mod.vk, S_mod.IP(S_mod.vk))

    if 0:
       # plot again, now the stellar template can be interpolated
       gplot(np.exp(xj), iod_j, S_star(xj), 'w l lc 9, "" us 1:3 w l lc 3')

    #gplot(np.exp(xj), iod_j, S_star(xj+3/c), 'w l lc 9 t "iodine", "" us 1:3 w l lc 3 t "template + 3 km/s",', np.exp(xj_eff), S_eff(xj_eff), 'w l lc 1 t "IP x (tpl*I2)"')

    # Now wavelength solution

    # mapping between pixel and wavelength

    #lam(x) = b0 + b_1 * x + b_2 * x**2
    lam = np.poly1d([w_i[0], (w_i[-1]-w_i[0])/w_i.size][::-1])

    # trim the observation to a range valid for the model
    s_obs = slice(*np.searchsorted(np.log(w_i), [xj[0]+100/c, xj[-1]-100/c]))

    # well, we see the wavelength solution can be improved
    #gplot(i[s_obs], S_eff(np.log(lam(i[s_obs]))), 'w l,', i, f_i, 'w lp pt 7 ps 0.5 lc 3')

    # and let's plot the observation against wavelength

    #gplot(np.exp(xj_eff), S_eff(xj_eff), 'w l,', lam(i), f_i, 'w lp pt 7 ps 0.5 lc 3')

    # a parameter set
    v = 0
    a = [0.96]
    b = [w_i[0], (w_i[-1]-w_i[0])/w_i.size] # [6128.8833940969, 0.05453566108124]
    s = 2.5

    # a simple call to the forward model
    Si_mod = S_mod(i[s_obs], v=0, a=[1], b=b, s=s)

    #gplot(i, Si_mod, 'w l t "S(i)",', i, f_i, 'w lp pt 7 ps 0.5 lc 3 t "S_i"')
    show_model(i[s_obs], f_i[s_obs], Si_mod, res=False)

    # A wrapper to fit the continuum
    S_a = lambda x, a0: S_mod(x, v, [a0], b, s)
    a, e_a = curve_fit(S_a, i[s_obs], f_i[s_obs])
    show_model(i[s_obs], f_i[s_obs], S_a(i[s_obs],*a), res=False)

    # A wrapper to fit the wavelength solution
    S_b = lambda x, b0,b1,b2,b3: S_mod(x, v, a, [b0,b1,b2,b3], s)

    v = v0   # a good guess for the stellar RV is needed
    bg = np.polyfit(i[s_obs], w_i[s_obs], 3)[::-1]
    b, e_b = curve_fit(S_b, i[s_obs], f_i[s_obs], p0=bg)
    bg1 = b*1

    #show_model(i[s_obs], f_i[s_obs], S_b(i[s_obs], *bg))
    #show_model(i[s_obs], f_i[s_obs], S_b(i[s_obs], *b))
    #gplot+(i[s_obs], S_star(np.log(np.poly1d(b[::-1])(i[s_obs]))+(v)/c), 'w lp ps 0.5')

    # compare the wavelength solutions
    #show_model(i, np.poly1d(b[::-1])(i), np.poly1d(bg[::-1])(i), res=True)

    # fit v, a and b simulatenously

    S_vab = lambda x, v, a, b0,b1,b2,b3: S_mod(x, v, [a], [b0,b1,b2,b3], 2.2)
    p_vab, e_p = curve_fit(S_vab, i[s_obs], f_i[s_obs], p0=[v, 1, *bg])
    show_model(i[s_obs], f_i[s_obs], S_vab(i[s_obs], *p_vab))

    s_obs = slice(400,1700) # probbably the wavelength solution of the template is bad
    # TLS spectra have a kink in continuum  at about 1700

    S_va = lambda x, v, a, b0,b1,b2,b3: S_mod(x, v, [a], [b0,b1,b2,b3], 2.2)
    p_va, e_p = curve_fit(S_va, i[s_obs], f_i[s_obs], p0=[v, 1,*p_vab[2:6]])
    p_va[0], np.diag(e_p)[0]**0.5
    show_model(i[s_obs], f_i[s_obs], S_va(i[s_obs], *p_va))

    S_vabs = lambda x, v, a, b0,b1,b2,b3, s: S_mod(x, v, [a], [b0,b1,b2,b3], s)
    p_vabs, e_p_vabs = curve_fit(S_vabs, i[s_obs], f_i[s_obs], p0=[*p_va, 2.2], epsfcn=1e-12)
    rvo, e_rvo = p_vabs[0], np.diag(e_p_vabs)[0]**0.5
    print(o, rvo, e_rvo)
    show_model(i[s_obs], f_i[s_obs], S_vabs(i[s_obs], *p_vabs))

    S = lambda x, v, a0,a1,a2,a3, b0,b1,b2,b3, s: S_mod(x, v, [a0,a1,a2,a3], [b0,b1,b2,b3], s)
    p_vabs, e_p_vabs = curve_fit(S, i[s_obs], f_i[s_obs], p0=[*p_vabs[:2]]+[0]*3+[*p_vabs[2:]], epsfcn=1e-12)
    rvo, e_rvo = p_vabs[0], np.diag(e_p_vabs)[0]**0.5
    print(o, rvo, e_rvo)
    show_model(i[s_obs], f_i[s_obs], S(i[s_obs], *p_vabs))

    #show_model(i[s_obs], f_i[s_obs], S_b(i[s_obs], *bg))
    #show_model(i[s_obs], f_i[s_obs], S_vabs(i[s_obs], *p))
    #gplot+(i[s_obs], S_star(np.log(np.poly1d(b[::-1])(i[s_obs]))+(v)/c), 'w lp ps 0.5')
    pause()  # globals().update(locals())
    return rvo, e_rvo

for i_o, o in enumerate(orders):
    rv[i_o], e_rv[i_o] = fit_chunk(o)

ii = np.isfinite(e_rv)
RV = np.mean(rv[ii]) 
e_RV = np.std(rv[ii])/(ii.sum()-1)**0.5
print('RV:', RV,e_RV)

rvounit = open('tmp.rvo.dat', 'w')
bjd = 0. 
print (bjd, RV, e_RV, *sum(zip(rv, e_rv),()), file=rvounit)
rvounit.close()


vpr.plot_rvo(rv, e_rv)
pause()

print('Done.')
