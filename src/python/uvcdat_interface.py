#!/usr/local/uvcdat/1.3.1/bin/python

# Functions callable from the UV-CDAT GUI.

import hashlib, os, pickle, sys, os
import cdutil.times
from filetable import *
from findfiles import *
from reductions import *
from plot_data import plotspec
from pprint import pprint

def setup_filetable( search_path, cache_path, ftid=None, search_filter=None ):
    """Returns a file table (an index which says where you can find a variable) for files in the
    supplied search path, satisfying the optional filter.  It will be useful if you provide a name
    for the file table, the string ftid.  For example, this may appear in names of variables to be
    plotted.  This function will cache the file table and
    use it if possible.  If the cache be stale, call clear_filetable()."""
    search_path = os.path.abspath(search_path)
    cache_path = os.path.abspath(cache_path)
    if ftid is None:
        ftid = os.path.basename(search_path)
    csum = hashlib.md5(search_path+cache_path).hexdigest()  #later will have to add search_filter
    cachefilename = csum+'.cache'
    cachefile=os.path.normpath( cache_path+'/'+cachefilename )

    if os.path.isfile(cachefile):
        f = open(cachefile,'rb')
        filetable = pickle.load(f)
        f.close()
    else:
        datafiles = treeof_datafiles( search_path, search_filter )
        filetable = basic_filetable( datafiles, ftid )
        f = open(cachefile,'wb')
        pickle.dump( filetable, f )
        f.close()
    return filetable

def clear_filetable( search_path, cache_path, search_filter=None ):
    """Deletes (clears) the cached file table created by the corresponding call of setup_filetable"""
    search_path = os.path.abspath(search_path)
    cache_path = os.path.abspath(cache_path)
    csum = hashlib.md5(search_path+cache_path).hexdigest()  #later will have to add search_filter
    cachefilename = csum+'.cache'
    cachefile=os.path.normpath( cache_path+'/'+cachefilename )

    if os.path.isfile(cache_path):
        os.remove(cache_path)

class uvc_plotspec():
    """This is a simplified version of the plotspec class, intended for the UV-CDAT GUI.
    Once it stabilizes, I may replace the plotspec class with this one.
    The plots will be of the type specified by presentation.  The data will be the
    variable(s) supplied, and their axes.  Optionally one may specify a list of labels
    for the variables, and a title for the whole plot."""
    # re prsentation (plottype): Yvsx is a line plot, for Y=Y(X).  It can have one or several lines.
    # Isofill is a contour plot.  To make it polar, set projection=polar.  I'll
    # probably communicate that by passing a name "Isofill_polar".
    def __init__( self, vars, presentation, labels=[], title='' ):
        self.presentation = presentation
        self.vars = vars
        self.labels = labels
        self.title = title
    def __repr__(self):
        return ("uvc_plotspec %s: %s\n" % (self.presentation,self.title,self.labels))

class one_line_plot( plotspec ):
    def __init__( self, yvar, xvar=None ):
        # xvar, yvar should be the actual x,y of the plot.
        # xvar, yvar should already have been reduced to 1-D variables.
        # Normally y=y(x), x is the axis of y.
        if xvar is None:
            xvar = yvar.getAxisList()[0]
        plotspec.__init__( self, xvars=[xvar], yvars=[yvar],
                           vid = yvar.id+" line plot", plottype='Yvsx' )

class two_line_plot( plotspec ):
    def __init__( self, y1var, y2var, x1var=None, x2var=None ):
        # x?var, y?var should be the actual x,y of the plots.
        # x?var, y?var should already have been reduced to 1-D variables.
        # Normally y?=y(x?), x? is the axis of y?.
        plotspec.__init__( self, y1vars=[y1var], y2vars=[y2var],
                           vid = y1var.variableid+y2var.variableid+" line plot", plottype='Yvsx' )

class one_line_diff_plot( plotspec ):
    def __init__( self, y1var, y2var, vid ):
        # y?var should be the actual y of the plots.
        # y?var should already have been reduced to 1-D variables.
        # y?=y(x?), x? is the axis of y?.
        plotspec.__init__( self,
            xvars=[y1var,y2var], xfunc = latvar_min,
            yvars=[y1var,y2var],
            yfunc=aminusb_1ax,   # aminusb_1ax(y1,y2)=y1-y2; each y has 1 axis, use min axis
            vid=vid,
            plottype='Yvsx' )

class plot_set3():
    """represents one plot from AMWG Diagnostics Plot Set 3.
    Each such plot is a pair of plots: a 2-line plot comparing model with obs, and
    a 1-line plot of the model-obs difference.  A plot's x-axis is latitude, and
    its y-axis is the specified variable.  The data presented is a climatological mean - i.e.,
    time-averaged with times restricted to the specified season, DJF, JJA, or ANN."""
    # N.B. In plot_data.py, the plotspec contained keys identifying reduced variables.
    # Here, the plotspec contains the variables themselves.
    def __init__( self, filetable1, filetable2, varid, seasonid ):
        """filetable1, filetable2 should be filetables for model and obs.
        varid is a string, e.g. 'TREFHT'.  Seasonid is a string, e.g. 'DJF'."""
        season = cdutil.times.Seasons(seasonid)
        self._var_baseid = '_'.join([varid,seasonid,'set3'])   # e.g. CLT_DJF_set3
        y1var = reduced_variable(
            variableid=varid,
            filetable=filetable1,
            reduction_function=(lambda x,vid=None: reduce2lat_seasonal(x,season,vid=vid)) )
        y2var = reduced_variable(
            variableid=varid,
            filetable=filetable2,
            reduction_function=(lambda x,vid=None: reduce2lat_seasonal(x,season,vid=vid)) )
        self.plot_a = two_line_plot( y1var, y2var )
        vid = '_'.join([self._var_baseid,filetable1._id,filetable2._id,'diff'])
        # ... e.g. CLT_DJF_set3_CAM456_NCEP_diff
        self.plot_b = one_line_diff_plot( y1var, y2var, vid )
    def results(self):
        # At the moment this is very specific to plot set 3.  Maybe later I'll use a
        # more general method, to something like what's in plot_data.py, maybe not.
        # later this may be something more specific to the needs of the UV-CDAT GUI
        y1var = self.plot_a.y1vars[0]
        y2var = self.plot_a.y2vars[0]
        y1val = y1var.reduce()
        y1unam = y1var._filetable._id  # unique part of name for y1, e.g. CAM456
        y1val.id = '_'.join([self._var_baseid,y1unam])  # e.g. CLT_DJF_set3_CAM456
        y2val = y2var.reduce()
        y2unam = y2var._filetable._id  # unique part of name for y2, e.g. NCEP
        y2val.id = '_'.join([self._var_baseid,y2unam])  # e.g. CLT_DJF_set3_NCEP
        ydiffval = apply( self.plot_b.yfunc, [y1val,y2val] )
        ydiffval.id = '_'.join([self._var_baseid, y1var._filetable._id, y2var._filetable._id,
                                'diff'])
        # ... e.g. CLT_DJF_set3_CAM456_NCEP_diff
        plot_a_val = uvc_plotspec(
            [y1val,y2val],'Yvsx', labels=[y1unam,y2unam],
            title=' '.join([self._var_baseid,y1unam,'and',y2unam]) )
        plot_b_val = uvc_plotspec(
            [ydiffval],'Yvsx', labels=['difference'],
            title=' '.join([self._var_baseid,y1unam,'-',y2unam]))
        return [ plot_a_val, plot_b_val ]


# TO DO: reset axes, set 'x' or 'y' attributes, etc., as needed

if __name__ == '__main__':
   if len( sys.argv ) > 1:
      from findfiles import *
      path1 = sys.argv[1]
      filetable1 = setup_filetable(path1,os.environ['PWD'])
      if len( sys.argv ) > 2:
          path2 = sys.argv[2]
      else:
          path2 = None
      if len(sys.argv)>3 and sys.argv[3].find('filt=')==0:  # need to use getopt to parse args
          filt2 = sys.argv[3]
          filetable2 = setup_filetable(path2,os.environ['PWD'],search_filter=filt2)
      else:
          filetable2 = setup_filetable(path2,os.environ['PWD'])
      ps3 = plot_set3( filetable1, filetable2, 'TREFHT', 'DJF' )
      print "ps3=",ps3
      pprint( ps3.results() )
   else:
      print "usage: plot_data.py root"
else:
    # My usual command-line test is:
    # ./uvcdat_interface.py /export/painter1/cam_output/*.xml ./obs_data/ filt="f_startswith('LEGATES')"
    path1 = '/export/painter1/cam_output/b30.009.cam2.h0.06.xml'
    path2 = '/export/painter1/metrics/src/python/obs_data/'
    filt2="filt=f_startswith('LEGATES')"
    filetable1 = setup_filetable(path1,os.environ['PWD'])
    filetable2 = setup_filetable(path2,os.environ['PWD'],search_filter=filt2)
    ps3 = plot_set3( filetable1, filetable2, 'TREFHT', 'DJF' )
    res3 = ps3.results()
