import numpy as np
from scipy.optimize import curve_fit
from scipy.special import erf
from astropy.modeling.models import Voigt1D

from gplot import *

c = 3e5   # [km/s] speed of light

# IP sampling in velocity space
# index k for IP space
def IP(vk, s=2.2):
    """Gaussian IP"""
    IP_k = np.exp(-(vk/s)**2/2)
    IP_k /= IP_k.sum()          # normalise IP
    return IP_k

def IP_sg(vk, s=2.2, e=2.):
    """super Gaussian"""
    IP_k = np.exp(-abs(vk/s)**e)
    IP_k /= IP_k.sum()          # normalise IP
    return IP_k

def IP_ag(vk, s=2.2, a=0):
    '''
    Asymmetric (skewed) Gaussian.

    Example
    -------
    >>> vk = np.arange(-50, 50+1)
    >>> gplot(vk, IP_ag(vk, s=10.), IP_ag(vk, s=10., a=100), ', "" us 1:3, "" us 1:($3-$2)*0.5, 0')

    '''
    #a = 10 * np.tanh(a)   # restrict asymmetry parameter to -10 and 10
    b = a / np.sqrt(1+a**2) * np.sqrt(2/np.pi)
    ss = s / np.sqrt(1-b**2)    # readjust scale parameter to have same variance as unskewed Gaussian
    vk = (vk + ss*b) / ss       # recenter to have zero mean
    IP_k = np.exp(-vk**2/2) * (1+erf(a/np.sqrt(2)*vk))   # Gauss IP * erf
    IP_k /= IP_k.sum()          # normalise IP
    return IP_k

def IP_bg(vk, s1=2., s2=2.):
    """BiGaussian"""
    # center of half-normal distribution Gaussians:   x1 = s1 * sqrt(2/pi)
    xc = np.sqrt(2/np.pi) * (-s1**2 + s2**2) / (s1+s2)   # area weights are the reciproke of the normalisation factors w1 = 1 / (sqrt(2/pi)*s1)
    vck = vk + xc               # to recenter the distribution
    IP_k = np.exp(-0.5*(vck/np.where(vck<0, s1, s2))**2)
    IP_k /= IP_k.sum()          # normalise IP
    return IP_k

def IP_mcg(vk, s0=2, a1=0.1):
    """IP for multiple, central Gaussians."""
    s1 = 4 * s0    # width of second Gaussian with fixed relative width
    a1 = a1 / 10   # relative ampitude
    IP_k = np.exp(-(vk/s0)**2)         # main Gaussian
    IP_k += a1 * np.exp(-(vk/s1)**2)   # background Gaussian
    IP_k = IP_k.clip(0, None)
    IP_k /= IP_k.sum()          # normalise IP
    return IP_k

def IP_mg(vk, *a):
    """IP for multiple uniformly spaced Gaussians ("Gaussian spline")."""
    s = 0.9        # fixed (yet hardcoded) width for all Gaussians (should be smaller than inst resolution)
    dx = s         # spacing between Gaussians
    na = len(a) + 1
    mid = len(a) // 2
    a = np.tanh(a)   # sigmoid, limit coeffs between -1 and 1
    a = [*a[:mid], 1, *a[mid:]]   # insert unit amplitude for central Gaussian
    xl = np.arange(na)            # knot numbers
    # center of infinite long and infinite oversampled IP (easy, since sigma is the same)
    xm = np.dot(xl, a) / sum(a)

    xc = (dx * (xl-xm))[:,np.newaxis]   # knot positions, recentered for zero mean IP
    IP_k = np.exp(-((vk-xc)/s)**2)      # matrix of displaced Gaussian base functions
    IP_k = np.dot(a, IP_k)              # multiply with amplitudes and sum up
    # IP_k = IP_k.clip(0, None)         # should we allow for negative IP values?
    IP_k /= IP_k.sum()                  # normalise IP
    # np.dot(IP_k,vk) / np.sum(IP_k)    # mean of the discrete, truncated IP should be ~0
    # gplot(IP_k)
    return IP_k

IPs = {'g': IP, 'sg': IP_sg, 'ag': IP_ag, 'bg': IP_bg, 'mg': IP_mg, 'mcg': IP_mcg, 'bnd': 'bnd'}


def poly(x, a):
    # redefine polynomial for argument order and adjacent coefficients
    return np.polyval(a[::-1], x)

def pade(x, a, b):
    '''
    rational polynomial
    b: denominator coefficients b1, b2, ... (b0 is fixed to 1)
    '''
    y = poly(x, a) / (1+x*poly(x, b))
    return y


class model:
    '''
    The forward model.

    '''
    def __init__(self, *args, func_norm=poly, IP_hs=50, xcen=0):
        # IP_hs: Half size of the IP (number of sampling knots).
        # xcen: Central pixel (to center polynomial for numeric reason).

        self.xcen = xcen
        self.S_star, self.lnwave_j, self.spec_cell_j, self.fluxes_molec, self.IP = args
        # convolving with IP will reduce the valid wavelength range
        self.dx = self.lnwave_j[1] - self.lnwave_j[0]   # step size of the uniform sampled grid
        self.IP_hs = IP_hs
        self.vk = np.arange(-IP_hs, IP_hs+1) * self.dx * c
        self.lnwave_j_eff = self.lnwave_j[IP_hs:-IP_hs]    # valid grid
        self.func_norm = func_norm
        #print("sampling [km/s]:", self.dx*c)

    def __call__(self, pixel, rv, coeff_norm, coeff_wave, coeff_ip, coeff_atm, coeff_bkg=[0]):

        spec_gas = 1 * self.spec_cell_j

        if len(self.fluxes_molec):
            # telluric forward modelling
            flux_atm = np.ones(len(self.fluxes_molec[0]))
            for coeff_mol, flux_mol in zip(coeff_atm, self.fluxes_molec):
                flux_atm *= flux_mol**np.abs(coeff_mol)

            # variable telluric wavelength shift; one shift for all molecules
            if len(coeff_atm) == len(self.fluxes_molec)+1:
                flux_atm = np.interp(self.lnwave_j, self.lnwave_j-np.log(1+coeff_atm[-1]/c), flux_atm)

            spec_gas *= flux_atm

        # IP convolution
        Sj_eff = np.convolve(self.IP(self.vk, *coeff_ip), self.S_star(self.lnwave_j-rv/c) * (spec_gas + coeff_bkg[0]), mode='valid')

        # wavelength relation
        #    lam(x) = b0 + b1 * x + b2 * x^2
        lnwave_obs = np.log(poly(pixel-self.xcen, coeff_wave))

        # sampling to pixel
        Si_eff = np.interp(lnwave_obs, self.lnwave_j_eff, Sj_eff)

        # flux normalisation
        Si_mod = self.func_norm(pixel-self.xcen, coeff_norm) * Si_eff
        #Si_mod = self.func_norm((np.exp(lnwave_obs)-b[0]-coeff_norm[-1]), coeff_norm[:-1]) * Si_eff
        return Si_mod

    def fit(self, pixel, spec_obs, par_rv=None, par_norm=[], par_wave=[], par_ip=[], par_atm=[], par_bkg=[], parfix_rv=None, parfix_norm=[], parfix_wave=[], parfix_ip=[], parfix_atm=[], parfix_bkg=[], sig=[], **kwargs):
        '''
        Generic fit wrapper.
        '''
        parfix_rv = () if parfix_rv is None else (parfix_rv,)
        par_rv = () if par_rv is None else (par_rv,)
        sv = slice(0, len(par_rv))
        sa = slice(sv.stop, sv.stop+len(par_norm))
        sb = slice(sa.stop, sa.stop+len(par_wave))
        ss = slice(sb.stop, sb.stop+len(par_ip))
        st = slice(ss.stop, ss.stop+len(par_atm))
        sc = slice(st.stop, st.stop+len(par_bkg))
        parfix_norm = tuple(parfix_norm)
        parfix_wave = tuple(parfix_wave)
        parfix_ip = tuple(parfix_ip)
        parfix_atm = tuple(parfix_atm)
        parfix_bkg = tuple(parfix_bkg)

        S_model = lambda x, *params: self(x, *params[sv]+parfix_rv, params[sa]+parfix_norm, params[sb]+parfix_wave, params[ss]+parfix_ip, params[st]+parfix_atm, params[sc]+parfix_bkg)

        params, e_params = curve_fit(S_model, pixel, spec_obs, p0=[*par_rv, *par_norm, *par_wave, *par_ip, *par_atm, *par_bkg], sigma=sig, absolute_sigma=False, epsfcn=1e-12)

        par_rv = (*params[sv], *np.diag(e_params)[sv])
        params = tuple(params)
        params = [*params[sv]+parfix_rv, params[sa]+parfix_norm, params[sb]+parfix_wave, params[ss]+parfix_ip, params[st]+parfix_atm, params[sc]+parfix_bkg]

        if kwargs:
            self.show(params, pixel, spec_obs, par_rv=par_rv, **kwargs)
        return params, e_params

    def show(self, params, x, y, par_rv=None, res=True, x2=None, dx=None, rel_fac=None):
        '''
        res: Show residuals.
        x2: Values for second x axis.
        rel_fac: Factor for relative residuals.
        dx: Subpixel step size for the model [pixel].
        '''
        ymod = self(x, *params)
        if x2 is None:
            x2 = np.poly1d(params[2][::-1])(x-self.xcen)
        if par_rv:
            gplot.RV2title(", v=%.2f ± %.2f m/s" % (par_rv[0]*1000, np.sqrt(par_rv[1])*1000))

        gplot.put("if (!exists('lam')) {lam=1}")

        gplot.key('horizontal')
        gplot.xlabel('lam?"Vacuum wavelength [Å]":"Pixel x"')
        gplot.ylabel('"flux"')
        # toggle between pixel and wavelength with shortcut "$"
        gplot.bind('"$" "lam=!lam; set xlabel lam?\\"Vacuum wavelength [Å]\\":\\"Pixel x\\"; replot"')
        args = (x, y, ymod, x2, 'us lam?4:1:2:3 w lp pt 7 ps 0.5 t "S_i",',
          '"" us lam?4:1:3 w p pt 6 ps 0.5 lc 3 t "S(i)"')
        prms = np.nan   # percentage prms
        if dx:
            xx = np.arange(x.min(), x.max(), dx)
            xx2 = np.poly1d(params[2][::-1])(xx-self.xcen)
            yymod = self(xx, *params)
            args += (",", xx, yymod, xx2, 'us lam?3:1:2 w l lc 3 t ""')
        if res or rel_fac:
            # linear or relative residuals
            col2 = rel_fac * np.mean(ymod) * (y/ymod - 1) if rel_fac else y - ymod
            rms = np.std(col2)
            prms = rms / np.mean(ymod) * 100
            gplot.mxtics().mytics().my2tics()
        if res:
            args += (",", x, col2, x2, "us lam?3:1:2 w p pt 7 ps 0.5 lc 1 t 'res (%.3g \~ %.3g%%)', 0 lc 3 t ''" % (rms, prms))
        if rel_fac:
            args += (",", x, col2, x2, "us lam?3:1:2 w l lc 1 t 'res (%.3g \~ %.3g%%)', 0 lc 3 t ''" % (rms, prms))

        gplot(*args)
        return prms


class model_bnd(model):
    '''
    The forward model with band matrix.

    '''
    def base(self, x=None, degk=3, sig_k=1):
        '''
        Setup the base functions.
        '''
        self.x = x
        bg = self.IP
        # the initial trace
        lnwave_obs = np.log(np.poly1d(bg[::-1])(x-self.xcen))
        j = np.arange(self.lnwave_j.size)
        jx = np.interp(lnwave_obs, self.lnwave_j, j)
        # position of Gaussians
        vl = np.array([-1, 0, 1])[np.newaxis,np.newaxis,:]
        vl = np.array([-1.4, -0.7, 0, 0.7, 1.4])[np.newaxis,np.newaxis,:]
        #vl = np.array([0])[np.newaxis,np.newaxis,:]

        # bnd -- lists all j's contributing to x
        self.bnd = jx[:,np.newaxis].astype(int) + np.arange(-self.IP_hs, self.IP_hs+1)

        # base for multi-Gaussians
        self.BBxjl = np.exp(-(self.lnwave_j[self.bnd][...,np.newaxis]-lnwave_obs[:,np.newaxis,np.newaxis]+sig_k*vl)**2/sig_k**2)

        # base function for flux polynomial
        self.Bxk = np.vander(x-x.mean(), degk)[:,::-1]
        #Bxk = np.vander(jx-jx.mean(), len(ak))[:,::-1]   # does not provide proper output for len(ak) > 4

    def Axk(self, v, **kwargs):
        if kwargs:
            self.base(**kwargs)
        starj = self.S_star(self.lnwave_j-v/c)  # np.interp(self.lnwave_j, np.log(tpl_w)-berv/3e5, tpl_f/np.median(tpl_f))
        _Axkl = np.einsum('xj,xjl,xk->xkl', (starj*self.spec_cell_j)[self.bnd], self.BBxjl, self.Bxk)
        return _Axkl

    def IPxj(self, akl, **kwargs):
        if kwargs:
            self.base(**kwargs)
        # sum all Gaussians
        IPxj = np.einsum('xjl,xk,kl->xj', self.BBxjl, self.Bxk, akl.reshape(self.Bxk.shape[1], -1)) #.reshape(AAxkl[0].shape))
        return IPxj

    def fit(self, f, v, **kwargs):
        Axkl = self.Axk(v, **kwargs)
        return np.linalg.lstsq(Axkl.reshape((len(Axkl), -1)), f, rcond=1e-32)

    def __call__(self, x, v, ak, **kwargs):
        Axkl = self.Axk(v, **kwargs)
        # dl = np.array([0.5, 2, 0.5])   # amplitude of Gaussian
        #ak = np.array([1, 0, 0, 0, 0])
        #fx = Axk @ ak
        # fx = AAxkl.reshape((len(AAxkl), -1)) @ aakl
        fx = Axkl.reshape((len(Axkl), -1)) @ ak
        return fx


def show_model(x, y, ymod, res=True):
    gplot(x, y, ymod, 'w lp pt 7 ps 0.5 t "S_i",',
          '"" us 1:3 w lp pt 6 ps 0.5 lc 3 t "S(i)"')
    if res:
        rms = np.std(y-ymod)
        gplot.mxtics().mytics().my2tics()
        # overplot residuals
        gplot.y2range('[-0.2:2]').ytics('nomirr').y2tics()
        gplot+(x, y-ymod, "w p pt 7 ps 0.5 lc 1 axis x1y2 t 'res %.3g', 0 lc 3 axis x1y2" % rms)
