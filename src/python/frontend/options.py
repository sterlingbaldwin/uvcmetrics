
### TODO: Fix compress options (in init or whatever)
### TODO: Seperate subclasses for datasets vs obs


import cdms2, os, logging, pdb, getpass
import metrics.packages as packages
import argparse, re
from metrics.frontend.defines import *
import logging
logger = logging.getLogger(__name__)


### This is subject to change, so it is at the top of the file
help_url="https://acme-climate.atlassian.net/wiki/pages/viewpage.action?pageId=11010895"

### 2 types of "options" - global options that affect program execution, etc
### and dataset-specific options that define a given dataset.
### Dataset options:
###  path
###  type (model vs obs)
###  climatology (vs raw data)
###  shortname (optional but a simple name to use on titles, etc)
###  filter (optional, defines a filter given a path for this specific subset of the path
###  start (optional, a starting time to process for this dataset)
###  end (optional, an ending time to process for this dataset)

### Global options:
###  package name (amwg vs lmwg vs ... )
###  compress (output is compressed)
###  times - seasonally, monthly, yearly, and the total list thereof
###  output options, primarily when running diags.py:
###   xml - output xml files?
###   netcdf - output netcdf files?
###   plots - output png files?
###   antialiasing - tun antialiasing off (for test suites really)
###   json - output json files
###  sets - which sets to plot
###  translate - optional list of {set 1} to {set N} variable name mapping translations, e.g. TSA->TREFHT
###  cachepath - path for cached data (*.cache), and cdscan output (*.xml).
###  vars - list of variables or ALL
###  varopts - list of variable options
###  regions -  list of regions

### Datasets can be defined as follows.
# 1) Explicitly pass in all arguments:
#    --path foo --type model --climatology no --shortname foo --filter none --start none --end none --bounds none
# 2) Pass in the required arguments only:
#   --path foo --type model
# 3) A comma-delimited list after --dataset of key=value pairs:
#  --dataset path=/path,type='model',climos='no',name='foo' ... etc
# 4) A colon-delimited list after --dataset of just the required parameters:
# --dataset path=/path,climos='no'

class Options():
    def __init__(self, runby='shell', **kwargs):
        # self._opts is the dictionary holding options.  But it can be accessed simply as self[key].
        self._opts = {}
        self.all_packages = packages.package_names

        # metadiags=True if we are running metadiags, or want to plain diags as if it were from
        # metadiags.  metadiags=False for multidiags.
        # The difference is whether defaults should be set here or by merging in options_defaults.
        # Normally, defaults come from options_defaults which is defined below.  A newly created
        # instance of Options should be merged with it; use self.merge(options_defaults).
        # This is automatically done when you call self.verifyOptions.
        if runby[0:4] in ['meta','Meta']:
            self['runby'] = runby[0:4]
            set_defaults = True
        elif runby[0:5] in ['shell','Shell']:
            self['runby'] = runby[0:5]
            set_defaults = True
        elif runby[0:5] in ['multi','Multi']:
            self['runby'] = runby[0:5]
            set_defaults = False
        if set_defaults:
            self._opts['model'] = []
            self._opts['obs'] = []
            self._opts['output'] = {} # output pre, post, directory, absolute filename, output options
            self._opts['times'] = [] # This is where seasonal/monthly/yearly choices end up
            self._opts['package'] = None
            self._opts['vars'] = ['ALL']
            self._opts['varopts' ] = None
            self._opts['sets'] = None
            self._opts['regions'] = []
            self._opts['logging'] = {}
            self._opts['uservars'] = []

            self._opts['reltime'] = None
            self._opts['cachepath'] = '/tmp/'+getpass.getuser()+'/uvcmetrics'
            self._opts['translate'] = True
            self._opts['translations'] = {}
            self._opts['levels'] = None
            self._opts['difflevels'] = None #levels for a difference plot
            self._opts['colormaps'] = {'model': 'viridis', 'obs': 'viridis', 'diff': 'bl_to_darkred'}
            self._opts['taskspernode'] = None
            self._opts["displayunits"] = None

            self._opts['output']['compress'] = True
            self._opts['output']['json'] = False
            self._opts['output']['xml'] = True
            self._opts['output']['netcdf'] = True
            self._opts['output']['plots'] = True
            self._opts['output']['antialiasing'] = True
            self._opts['output']['climos'] = True
            self._opts['output']['outputdir'] = '/tmp'
            self._opts['output']['prefix'] = ''
            self._opts['output']['postfix'] = ''
            self._opts['output']['logo'] = True
            self._opts['output']['table'] = False

            self._opts['logging']['level'] = logging.ERROR
            self._opts['logging']['file'] = None

            self._opts['dbhost'] = "https://diags-viewer.llnl.gov"
            self._opts['dsname'] = None
            self._opts['do_upload'] = False

        for key,value in kwargs.iteritems():
            self._opts[key] = value

    def clone( self, exception=None ):
        """Generates and returns an exact copy of the present instance of Options, if 'exception' is
        not supplied.  If the exception is supplied, it should be a 2-tuple: the first item is the
        name of an option and the second its value.  Then the returned Options instance will be an
        exact copy except for that option, where the supplied value will be used instead.
        This copy is shallow; that is, the dictionary self._opts is copied but its elements are not.
        """
        newopts = Options(runby=self['runby'])
        for key,value in self._opts.iteritems():
            newopts[key] = value
        if exception is not None:
            newopts[exception[0]] = exception[1]
        return newopts

    def merge( self, opt2 ):
        """Merge another instance of the Options class into this one.
        If they have a conflict over the value of any option, then this instance gets priority."""
        if opt2 is None:
            return
        for key,value in opt2._opts.iteritems():
            if key not in self._opts or self[key] is None:
                self[key] = value
            elif key in ['obs','model'] and self[key]==[]:
                self[key] = value
            elif key in ['output', 'logging', 'translations']:
                # For these options, the value is a dictionary which should be merged, not replaced.
                # Other dictionaries should generally be replaced (or not), not merged.
                for k,v in opt2[key].iteritems():
                    if k not in self[key].keys():
                        self[key][k] = v

    def merge_modobs( self, opt2, key ):
        """DEPRECATED Merges the model or obs option of two Options instances, self and opt2.
        key should be 'model' or 'obs'.
        This is generally needed only when the option self[key] hasn't been completely defined."""
        # A complete model/obs specification shouldn't be merged.  But usually they won't be
        # complete: missing the path, or only the path.  To prevent a merger, add a
        # 'merge':False item to the model/obs dict.  c.f. the checks below on self[key].get('merge',True)
        if key not in ['model','obs'] or len(opt2[key])<=0 :
            return
        # These options are composite, and complicated.  
        # At the moment I cannot properly merge two obs lists if the length is >1.
        if len(self[key])==0:
            self[key] = opt2[key]
        elif len(self[key])>=1 and len(opt2[key])==1:
            for idx,mob in enumerate(self[key]):   # mob is a dict with keys such as filter, path, climos
                if self[key].get('merge',True)==False:
                    continue
                for k,v in opt2[key][0].iteritems():
                    if k not in mob.keys() or mob[k] is None:
                        mob[k] = v
        elif len(self[key])==1 and len(opt2[key])>=1 and self[key][0].get('merge',True)!=False:
            self[key] = [ self[key][0].copy() for _ in opt2[key] ]
            for idx,mob in enumerate(opt2[key]):   # mob is a dict with keys such as filter, path, climos
                for k,v in mob.iteritems():
                    if k not in self[key][idx].keys() or self[key][idx][k] is None:
                        self[key][idx][k] = v
        elif len(self[key])>1 and len(opt2[key])>1:
            logger.error("Options.merge not implemented for model or obs lists both of length>1")

   # Some short cut getter/setters
    def __getitem__(self, opt):
        return self._opts[opt]

    def __setitem__(self, key, value):
        self._opts[key] = value

    def get(self, opt, default=None):
        return self._opts.get(opt,default)

    def keys(self):
        return self._opts.keys()

   ###
   ### The next 4 functions all process dataset/obs options.
   ###
    def processPaths(self, args):
        import sys
        progname = sys.argv[0]
        logger.info(progname)
        progname = progname.split('/')[-1]
        mid = 0
        oid = 0

        for i in range(len(args.path)):
            if args.type != None and len(args.type) >= i:
               if args.type[i] == 'model':
                   index = mid
                   key = 'model'
                   mid = mid + 1
               else:
                   index = oid
                   key = 'obs'
                   oid = oid + 1
            else: # assume no type == model data
                index = mid
                key = 'model'
                mid = mid + 1
            logger.info('Updating subentry %d of %d total', index, i)

        self._opts[key].append({})
        self._opts[key][index]['path'] = args.path[i]
        self._opts[key][index]['type'] = key


        if 'climatology' not in progname and 'climatology.py' not in progname:
           if args.climo != None and len(args.climo) >= i:
              if args.climo[i] in ['True', 'yes', 1]:
                  self._opts[key][index]['climo'] = True
              else:
                  self._opts[key][index]['climo'] = False
           else:
               self._opts[key][index]['climos'] = True

        if args.name != None and len(args.name) >= i:
            self._opts[key][index]['name'] = args.name[i]
        else:
            self._opts[key][index]['name'] = None

        if args.filters != None and len(args.filters) > i:
            if args.filters[i] in ['None', 'none', 'no']:
                self._opts[key][index]['filter'] = None
            else:
               self._opts[key][index]['filter'] = args.filters[i]
        else:
            self._opts[key][index]['filter'] = None

        if args.start != None and len(args.start) >= i:
            self._opts[key][index]['start'] = args.start[i]
        else:
            self._opts[key][index]['start'] = None

        if args.end != None and len(args.end) >= i:
            self._opts[key][index]['end'] = args.end[i]
        else:
            self._opts[key][index]['end'] = None
        logger.debug(self._opts[key][index])

    def processDataset(self, dictkey, data):
        defkeys = ['start', 'end', 'filter', 'name', 'climos', 'path', 'type']

        for i in range(len(data)):
            if dictkey not in self._opts:  #jfp
                self._opts[dictkey] = []
            self._opts[dictkey].append({})
            for d in defkeys:
                self._opts[dictkey][i][d] = None
            self._opts[dictkey][i]['type'] = dictkey  # ensure this one is at least set.
            kvs = data[i].split(',')
            PATTERN = re.compile(r'''((?:[^,"']|"[^"]*"|'[^']*')+)''')
            kvs = PATTERN.split(data[i])[1::2]
            for k in kvs:
                if '=' not in k:
                    logging.critical('All options need specified as {option}={value}. No equal sign in option - %s', k)
                    quit()
                key, value = k.split('=')
                if key in defkeys:
                    if key == 'climo':
                        if value in ['True', 'yes', 1]:
                            self._opts[dictkey][i][key] = True
                        else:
                            self._opts[dictkey][i][key] = False
                    else:
                        self._opts[dictkey][i][key] = value
                else:
                    logging.warning('Unknown option %s', k)
            logger.info('Added set: %s', self._opts[dictkey][i])

    def processLevels(self, ID, levels, altLEVELS):

        #this is a result of having a negative level
        if levels == []:
            levels = altLEVELS

        try:
            #check if levels is a file containing the actual levels
            f=open(levels, 'r')
            levels = f.read()
            f.close()
        except:
            pass

        try:
            #check levels are specified correctly
            if len(levels) == 1:
                levels = levels[0]
                sep = " "
                if "," in levels:
                    sep = ","
                levels = levels.split(sep)
            self._opts[ID] = [float(x) for x in levels]
            return
        except:
            pass

        logging.warning('%s Levels are not specified correctly.', levels)
        logging.critical('They must be delimited with all commas or all spaces list of numbers or a file name that contains the list.')
        quit()

    def processModel(self, models):
        self.processDataset('model', models) # the dtype and the dictionary key for it, the data
    def processObs(self, obs):
        self.processDataset('obs', obs)

    def processColormaps(self, ID, colormaps):
        import vcs, pdb, sys
        if colormaps == []:
            return
        key_value = [cm.split('=') for cm in colormaps]
        try:
            for plot_type, colormap in key_value:
                if os.path.exists(colormap):
                    #first see if it`s a script that loads a stored colormap
                    try:
                        #this puts the colormap in the master list of colormaps
                        vcs.scriptrun(colormap)
                    except:
                        pass

                #get colormap from master list
                if plot_type in self._opts[ID].keys() and colormap in vcs.listelements('colormap'):
                    self._opts[ID][plot_type] = colormap
                else:
                    raise

            # set obs color map to the models if not specified
            if self._opts[ID]['model'] != None and self._opts[ID]['obs'] == None:
                self._opts[ID]['obs'] = self._opts[ID]['model']

        except:
            logging.critical('Invalid color map: '+ colormap)
            logging.critical('Must be in this list: ' + ', '.join(vcs.listelements('colormap')))
            sys.exit()

    def processDisplayunits(self, ID, displayunits):
        """Check that the units are valid"""
        self._opts['output'][ID] = displayunits
        self._opts["displayunits"] = displayunits
        pass

    def processLogging(self, log_level, log_file):
        levels = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL
        }
        if log_level:
            if "logging" not in self.keys():
                self["logging"] = {}
            # Use whatever value is in there already as the default.
            if "level" not in self["logging"].keys():
                self["logging"]["level"] = options_defaults["logging"]["level"]
            self._opts["logging"]["level"] = levels.get(log_level.upper(), self._opts["logging"]["level"])
        if log_file:
            log_path = os.path.abspath(os.path.expanduser(log_file))
            self._opts["logging"]["file"] = log_path

    def processUservars( self, uservars ):
        self._opts["uservars"]=uservars

   ###
   ### The next few functions provide the ability to get valid options to the various parameters.
   ###
    def listSeasons(self):
        return all_seasons;

    def listTranslations(self):
        # Somewhere a list needs stored or generatable.
        # Is it going to be class specific? I think probably not, so it could be with all_months or all_seasons
        # or something similar.
        # also, allows the user to specify an arbitrary list. that should just get postpended to the existing list
        return

    def listSets(self, packageid, key=None):
        # I don't know of a better way to do this. I'd rather have these
        # defined (perhaps in defines.py)
        # it would clean up a lot of code here, and in amwg/lmwg I think.
        if packageid is None:
            logger.error("must specify package to list plot sets")
            quit()
        elif packageid.lower() == 'lmwg':
            import metrics.packages.lmwg.lmwg
            pinstance = metrics.packages.lmwg.lmwg.LMWG()
        elif packageid.lower() == 'amwg':
            import metrics.packages.amwg.amwg
            pinstance = metrics.packages.amwg.amwg.AMWG()
        diags = pinstance.list_diagnostic_sets()
        keys = diags.keys()
        keys.sort()
        sets = {}
        for k in keys:
            fields = k.split()
            sets[fields[0]] = ' '.join(fields[2:])
        return sets

    def listVariables(self, package, setname):
        import metrics.fileio.filetable as ft
        import metrics.fileio.findfiles as fi
        if setname is None:
            logger.error("must specify plot set to list variables")
            quit()
        dtree = fi.dirtree_datafiles(self, modelid=0)
        filetable = ft.basic_filetable(dtree, self)

        # this needs a filetable probably, or we just define the maximum list of variables somewhere
        if package is None:
            logger.error("must specify package to list variables")
            quit()
        elif package.lower() == 'lmwg':
            import metrics.packages.lmwg.lmwg
            pinstance = metrics.packages.lmwg.lmwg.LMWG()
        elif package.lower()=='amwg':
            import metrics.packages.amwg.amwg
            pinstance = metrics.packages.amwg.amwg.AMWG()

        slist = pinstance.list_diagnostic_sets()
        keys = slist.keys()
        keys.sort()
        vl = []
        for k in keys:
            fields = k.split()
            if setname[0] == fields[0]:
                vl = slist[k]._list_variables(filetable, filetable)
                logger.info('Available variables for set %s in package %s at path %s:', setname[0], package, self._opts['model'][0]['path'])
                logger.info(vl)
                logger.info('NOTE: Not all variables make sense for plotting or running diagnostics. Multi-word variable names need enclosed in single quotes:\'word1 word2\'')
                logger.info('ALL is a valid variable name as well')
        if vl == []:
            logging.critical('No variable list returned. Is set %s a valid set?',setname[0])
            quit()
        return

    def listVarOptions(self, package, setname, varname):
        import metrics.fileio.filetable as ft
        import metrics.fileio.findfiles as fi
        if setname is None:
            logger.error("must specify plot set to list variable options")
            quit()
        if varname is None:
            logger.error("must specify variable to list variable options")
            quit()
        dtree = fi.dirtree_datafiles(self, modelid=0)
        filetable = ft.basic_filetable(dtree, self)

        if package is None:
            logger.error("must specify package to list variable options")
            quit()
        elif package.lower() == 'lmwg':
            import metrics.packages.lmwg.lmwg
            pinstance = metrics.packages.lmwg.lmwg.LMWG()
        elif package.lower()=='amwg':
            import metrics.packages.amwg.amwg
            pinstance = metrics.packages.amwg.amwg.AMWG()

        slist = pinstance.list_diagnostic_sets()
        keys = slist.keys()
        keys.sort()
        for k in keys:
            fields = k.split()
            if setname[0] == fields[0]:
                vl = slist[k]._all_variables(filetable, filetable)
                for v in varname:
                   if v in vl.keys():
                       vo = vl[v].varoptions()
                       logger.debug('Variable %s in set %s from package %s at path %s has options:', v, setname[0], package, self._opts['model'][0]['path'])
                       logger.debug(vo)
                   else:
                        logger.debug('Variable %s in set %s from package %s at path %s has no options.', v, setname[0], package, self._opts['model'][0]['path'])


    ###
    ### This verifies a few command line options. It could probably use some more sanity checks
    ###
    def verifyOptions(self):

        # TODO Determine if path is a single file, e.g. a cdscan generated XML file or a directory
        # and if it is a directory, if there is already a .xml file, ignore it or not. Might
        # need an option for that ignore option?
        # Other thigns to (eventually) verify:
        #    1) Start/end years are valid and within the range specified
        import metrics.fileio.filetable as ft
        import metrics.fileio.findfiles as fi
        import metrics.packages.diagnostic_groups
        import os
        self.merge(options_defaults)  # jfp not really a "verify" step, but has to be done now that defaults are out of __init__
        if len(self._opts['model']) == 0 and len(self._opts['obs']) == 0:
            logging.critical('At least one model or obs set needs describted')
            quit()
        if len(self._opts['model']) != 0:
            for i in range(len(self._opts['model'])):
                if self._opts['model'][i]['path'] == None or self._opts['model'][i]['path'] == '':
                    logging.critical('Each dataset must have a path provided')
                    quit()
                # check if the path exists
                if not os.path.exists(self._opts['model'][i]['path']):
                    logging.critical('Path - %s - does not exist', self._opts['model'][i]['path'])
                    quit()
        if len(self._opts['obs']) != 0:
           for i in range(len(self._opts['obs'])):
               if self._opts['obs'][i]['path'] == None or self._opts['obs'][i]['path'] == '':
                   logging.critical('Each dataset must have a path provided')
                   quit()
               if not os.path.exists(self._opts['obs'][i]['path']):
                   logging.critical('Obs Path - %s - does not exist', self._opts['obs'][i]['path'])
                   quit()
        #      if(self._opts['package'] == None):
        #         print 'Please specify a package e.g. AMWG, LMWG, etc'
        #         quit()

        # A path is guaranteed, even if it is just /tmp. So check for it
        # We shouldn't get here anyway. This is primarily in case something gets postpended to the user-specified outputdir
        # in options(). Currently that happens elsewhere, but seems like a raesonable check to keep here anyway.
        if not os.path.exists(self._opts['output']['outputdir']):
            logging.critical('output directory %s does not exist', self._opts['output']['outputdir'])
            quit()

        if(self._opts['package'] != None):
            keys = self.all_packages.keys()
            ukeys = []
            for k in keys:
                ukeys.append(k.upper())

            if self._opts['package'].upper() not in ukeys:
                logging.critical('Package %s not found in the list of package names - %s', self._opts['package'], self.all_packages.keys())
                quit()

        # Should we check for random case too? I suppose.
        if(self._opts['regions'] != []):
            rlist = []
            for x in self._opts['regions']:
                if x in all_regions.keys():
                    rlist.append(x)
            rlist.sort()
            self._opts['regions'].sort()
            if rlist != self._opts['regions']:
                logging.critical('Unknown region[s] specified: %s', list(set(self._opts['regions']) - set(rlist)))
                quit()
        if(self._opts['sets'] != None and self._opts['package'] != None):
            sets = []
            package = self._opts['package']
            if package.lower() == 'lmwg':
                import metrics.packages.lmwg.lmwg
            elif package.lower()=='amwg':
                import metrics.packages.amwg.amwg
            dtree = fi.dirtree_datafiles(self, modelid=0)
            filetable = ft.basic_filetable(dtree, self)


        from metrics.graphics.default_levels import default_levels
        import amwgmaster, pdb

        if self._opts["levels"] is None:  # User did not specified options, let's auto this
            vr = self._opts["vars"][0]
            if self._opts["varopts"] is not None:
                vr=vr+"_%s" % self._opts["varopts"][0]
            if vr in default_levels:
                self._opts["levels"] = default_levels[vr].get("OBS",{}).get("contours",None)
            else:
                if vr in amwgmaster.diags_varlist:
                    vrlst = amwgmaster.diags_varlist[vr]
                    self._opts["levels"]=default_levels.get(vrlst.get("filekey","OH CRAP"),{}).get("OBS",{}).get("contours",None)
            if self._opts["levels"] is not None:
                self._opts["levels"].insert(0,-1.e20)
                self._opts["levels"].append(1.e20)

        if self._opts["difflevels"] is None:  # User did not specified options, let's auto this
            vr = self._opts["vars"][0]
            if self._opts["varopts"] is not None:
                vr=vr+"_%s" % self._opts["varopts"][0]
            if vr in default_levels:
                self._opts["difflevels"] = default_levels[vr].get("OBS",{}).get("difference",None)
            else:
                if vr in amwgmaster.diags_varlist:
                    vrlst = amwgmaster.diags_varlist[vr]
                    self._opts["difflevels"]=default_levels.get(vrlst.get("filekey","OH CRAP"),{}).get("OBS",{}).get("difference",None)
            if self._opts["difflevels"] is not None:
                self._opts["difflevels"].insert(0,-1.e20)
                self._opts["difflevels"].append(1.e20)

        if self._opts["displayunits"] is None:  # User did not specified options, let's auto this
            vr = self._opts["vars"][0]
            if self._opts["varopts"] is not None:
                vr=vr+"_%s" % self._opts["varopts"][0]
            if vr in default_levels:
                self._opts["displayunits"] = default_levels[vr].get("displayunits", None)

#######
####### This should be modified to look in the master dictionary files...
#######
#         pclass = dm[package.upper()]()
#
#         avail_sets = []
#         slist = pclass.list_diagnostic_sets()
#         keys = slist.keys()
#         keys.sort()
#         for k in keys:
#            fields = k.split()
#            avail_sets.append(fields[0])
#            for user in args.sets:
#               if user == fields[0]:
#                  sets.append(user)
#         sets = self._opts['sets']
#         intersect = list(set(sets)-set(avail_sets))
#         if intersect != []:
#            logging.critical('Collection(s) requested %s', sets)
#            logging.critical('Collection(s) available: %s', avail_sets)
#            quit()

   ### Less-verbose help for metadiags.
    def metadiags_help(self):
        print
        print "metadiags concise help. Use --extended-help for extended help."
        print "For additional instructions, see also"
        print help_url
        print
        print "Metadiags is meant to call diags.py (and other executables in \"loose coupling\" mode)"
        print " with appropriate arguments defined via the amwgmaster or lmwgmaster.py files"
        print
        print "Minimum required arguments:"
        print "1. A single path pointing to the input dataset"
        print "2. A path for output data"
        print "3. The package type, e.g. amwg or lmwg\n"
        print "All input paths (multiple models and/or obs) are specified in a similar fashion."
        print "The argument (--model or --obs) takes one or more comma-separated arguments to"
        print "describe the dataset"
        print "The only required argument is the path={path} argument"
        print "Optional additional arguments are:"
        print "climos=[yes|no] - Is the dataset raw data or summary climatology files? "
        print " Default is to assume the path contains climatology files"
        print "dsname={name} - An arbitrary user-defined name for the dataset."
        print " This is used in some plots and filenames. In addition, a path for raw data"
        print " and a path for climatology files can be specified for the same dataset if the"
        print " dsname is the same"
        print "For observation only: filter={filter}, for example - 'f_startswith(\"NCEP\")'"
        print "A simple example:"
        print "  metadiags --model path=/path/to/my/data --obs path=/path/to/all/obs/data \\"
        print "     --outputdir /path/to/output --package AMWG"
        print "This will run all of the defined diagnostics in amwgmaster.py on the data in "
        print " /path/to/my/data comparing with the appropriate observation file in "
        print " /path/to/all/obs/data and write the results to /path/to/output/amwg\n"
        print "A slightly more complicated example:"
        print "  metadiags --model path=/path/to/my/data/raw,climos=no,dsname=myds1 \\"
        print "     --model path=/path/to/my/data/climos,climos=yes,dsname=myds1 \\ "
        print "     --outputdir /path/to/output --package LMWG"
        print "This will use the climatology files for the dataset when possible and the"
        print " raw dataset data when required (e.g. if nonlinear calculations are performed)\n"
        print  "Frequently used optional arguments:"
        print "--colls - Specify which collection(s) to run. "
        print "--hostname and --dsname - Update the classic viewer database"
        print " with information from this run. You'll also need to run the transfer script"
        print " to actually move data over. These options are more fully documented elsewhere"
        return


   ### Less-verbose help for diags.
    def diags_help(self):
        print
        print 'diags concise help. Use --extended-help for extended help.'
        print "For additional instructions, see also"
        print help_url
        print
        print 'Minimum required arguments:'
        print '1. The --model keyword to describe the input dataset'
        print '2. A path for output data'
        print '3. The package type, e.g. lmwg or amwg'
        print '4. Which set/collection to run, e.g. "tier1b-so" or 5 or 14'
        print '5. (Optional) The variables of interest, e.g. Z3 TLAI PBOT. The default is ALL variables valid for the package/set/dataset'
        print '6. (Optional) The --obs keyword to describe observation dataset(s)'
        print '7. (Optional) Variable options such as seasons, regions, and pressure levels'
        print '8. (Optional) Levels can be specified for the model, obs and difference.  The model and obs are the same with --levels. The difference is --difflevels.'
        print '9. (Optional) Colormaps are specified for each plot with --colormaps model=xxx obs=yyy diff=zzz\n'
        print "All input paths (multiple models and/or obs) are specified in a similar fashion."
        print "The argument (--model or --obs) takes one or more comma-separated arguments to"
        print "describe the dataset"
        print "The only required argument is the path={path} argument"
        print "Optional additional arguments are:"
        print "climos=[yes|no] - Is the dataset raw data or summary climatology files? "
        print " Default is to assume the path contains climatology files"
        print "dsname={name} - An arbitrary user-defined name for the dataset."
        print " This is used in some plots and filenames. In addition, a path for raw data"
        print " and a path for climatology files can be specified for the same dataset if the"
        print " dsname is the same"
        print "For observation only: filter={filter}, for example - 'f_startswith(\"NCEP\")'"
        print 'The simplest example:'
        print 'diags --model path=/path/to/my/data --package AMWG --outputdir . --coll 5'
        print 'A slightly more complicated example:'
        print 'diags --model path=/path/to/my/raw/data,climos=no --package LMWG --outputdir . --coll 2 --seasons DJF SON --vars TLAI'
        print 'To specify levels use --levels 1,2,3 for the model and obs. Use --difflevels -2,-1,0,1,2 for the difference.'
        print 'To spcify the colormap use either a valid colormap or a file containing a colormap. To get a list of valid colormaps use --colormaps model=xxx. The valid colormaps will be printed.'
        return

    def climatology_help(self):
        print 'climatology concise help. Use --help for extended help'
        print 'Minimum required arguments:'
        print '1. The input path'
        print '2. The output path'
        print '3. The list of seasons'
        print '4. (optional) The list of variables (defaults to ALL)'





   ###
   ### This actually sets up argparse
   ###
    def processCmdLine(self, progname, parser):
        # There are 3 sets of command line arguments, depending on what is calling this function.
        # 1) climatology.py - just needs input path (assumes climos=no), output path, and optionally a list of seasons/variables. It can take a dsname too
        # 2) diags-new.py - takes every option
        # 3) meta-diags.py - takes model/path info, plus some extra options.

        # Dataset related stuff. All utilities get these.
        pathopts = parser.add_argument_group('Data')
        pathopts.add_argument('--path', '-p', action='append',
                              help="Path(s) to dataset(s). This is required if the --models/--obs options are not used.")
        pathopts.add_argument('--filters', '-f', action='append',
                              help="A filespec filter. This will be applied to the dataset path(s) (--path option) to narrow down file choices.. This is used if --model/--obs options are not.")
        pathopts.add_argument('--type', '-t', action='append', choices=['m','model','o','obs','observation'],
                              help="Specifies the type of this dataset. Options are 'model' or 'observation'. This is used if --model/--obs options are not.")
        pathopts.add_argument('--name', '-n', action='append',
                              help="A short name for this dataset. used to make titles and filenames manageable. This is used if --model/--obs options are not.")
        pathopts.add_argument('--start', action='append',
                              help="Specify a start time in the dataset. This is used if --model/--obs options are not.")
        pathopts.add_argument('--end', action='append',
                              help="Specify an end time in the dataset. This is used if --model/--obs options are not.")
        if 'climatology' not in progname and 'climatology.py' not in progname:
            pathopts.add_argument('--climo', '--climos', action='append', choices=['no','yes', 'raw','True', 'False'],
                                  help="Specifies whether this path is raw data or climatologies. This is used if --model/--obs options are not.")
        pathopts.add_argument('--model', '-m', action='append',# nargs=1,
                              help="key=value comma delimited list of model options. Options are as follows: path={a path to the data} filter={one or more file filters} name={short name for the dataset} start={starting time for the analysis} end={ending time for the analysis} climo=[yes|no] - is this a set of climatologies or raw data")
        pathopts.add_argument('--obs', '-O', action='append', #nargs=1,
                              help="key=value comma delimited list of observation options. See usage guide for more information.")
        pathopts.add_argument('--uservars', action='append',
                              help="a module defining user-defined derived variables; should be in your PYTHONPATH.  See the user guide for the file format.  This option may appear any number of times."),

        # Other options, useful at various times.
        otheropts = parser.add_argument_group('Other')
        otheropts.add_argument('--cachepath', nargs=1,
                               help="Path for cached files. Defaults to /tmp/<username>/uvcmetrics/")
        otheropts.add_argument('--obspath', nargs=1,
                               help="Path for obs files.")
        otheropts.add_argument('--modelpath', nargs=1,
                               help="Path for model files.")
        otheropts.add_argument('--verbose', action='count',
                               help="Increase the verbosity level. Each -v option increases the verbosity more.") # count
        otheropts.add_argument('--list', '-l', nargs=1, choices=['sets', 'vars', 'variables', 'packages', 'seasons', 'regions', 'translations','options','varopts'],
                               help="Determine which packages, sets, regions, and variables are available")
        otheropts.add_argument('-h', '--help', action='store_const', const=1,
                               help="Concise help screeen")
        otheropts.add_argument('--version',action='store_const', const=1,
                               help="Version information")
        otheropts.add_argument('--extended-help', action='store_const', const=1,
                               help="Extended/comprehensive help information")

        # Logging options
        log_opts = parser.add_argument_group("Logging")
        log_opts.add_argument('--log_level', action="store", choices=["debug", "info", "warning", "error", "critical", "INFO", "DEBUG", "WARNING", "ERROR", "CRITICAL"],
                              help="Level of logging information to display.")
        log_opts.add_argument('--log_file', action="store", help="Path to output file for logging (defaults to stdout).")

        # Runtime options.
        runopts = parser.add_argument_group('Runtime control')
        if 'climatology' not in progname and 'climatology.py' not in progname:
            runopts.add_argument('--package', '--packages', '-k',
                                 help="The diagnostic package to run against the dataset(s).")
            runopts.add_argument('--sets', '--set', '--colls', '--coll', '-s', nargs='+',
                                 help="The sets within a diagnostic package to run. Multiple sets can be specified.")
            runopts.add_argument('--varopts', nargs='+',
                                 help="Variable auxillary options")
            #levels for isofill plots

            runopts.add_argument('--levels', nargs='*',
                                 help="Specify a file name containing a list of levels or the comma delimited levels directly")
            runopts.add_argument('--difflevels', nargs='*',
                                 help="These levels are for a difference plot. Specification is the same as levels.")

            runopts.add_argument('--translate', nargs='?', default='y',
                                 help="Enable translation for obs sets to datasets. Optional provide a colon separated input to output list e.g. DSVAR1:OBSVAR1")
            runopts.add_argument('--dryrun',
                                  help="Do not run anything simply store list of commands in file table_commands.sh for diags or metadiags_commands.sh for metadiags",
                                  action="store_true")
            runopts.add_argument('--sbatch',
                                  help="Run sbatch with the specified number of nodes",
                                  default=0,
                                  type=int,
                                  )
            runopts.add_argument('--regrid',
                                 help="Regridder to use when necessary.  Possible values include esmf-linear, esmf-conserv, regrid2.",
                                 default="esmf-linear" )
            if 'metadiags' not in progname and 'metadiags.py' not in progname:
                runopts.add_argument('--vars', '--var', '-v', nargs='+',
                                     help="Specify variables of interest to process. The default is all variables which can also be specified with the keyword ALL")
                runopts.add_argument('--regions', '--region', nargs='+', choices=all_regions.keys(),
                                     help="Specify a geographical region of interest. Note: Multi-word regions need quoted, e.g. 'Central Canada'")
            else:
                runopts.add_argument('--custom_specs', default=None,
                                     help="points to a file that will contain a custom dictionary updation the diags specs, see amwgmaster.py")

        timeopts = parser.add_argument_group('Time Options')
        if 'metadiags' not in progname and 'metadiags.py' not in progname:
            # time-related options, primarily used in diags-new, but climatology.py too
            timeopts.add_argument('--seasons', nargs='+', choices=all_seasons,
                                  help="Specify which seasons to generate climatoogies for")
            timeopts.add_argument('--years', nargs='+',
                                  help="Specify which ears to include when generating climatologies")
            timeopts.add_argument('--months', nargs='+', choices=all_months,
                                  help="Specify which months to generate climatologies for")
            timeopts.add_argument('--seasonally', action='store_true',
                                  help="Produce climatologies for all of the defined seasons. To get a list of seasons, run --list seasons")
            timeopts.add_argument('--monthly', action='store_true',
                                  help="Produce climatologies for all predefined months")
            timeopts.add_argument('--yearly', action='store_true',
                                  help="Produce annual climatogolies for all years in the dataset")
            timeopts.add_argument('--timestart',
                                  help="Specify the starting time for the dataset, such as 'months since Jan 2000'")

        # Output options. These are universal
        outopts = parser.add_argument_group('Output')
           # maybe eventually add compression level too....
        outopts.add_argument('--compress', choices=['no', 'yes'],
                             help="Turn off netCDF compression. This can be required for other utilities to be able to process the output files (e.g. parallel netCDF based tools") #no compression, add self state
        outopts.add_argument('--outputdir', '-o',
                             help="Directory in which output files will be written." )


        if 'climatology' not in progname and 'climatology.py' not in progname:
            outopts.add_argument('--plots', choices=['no','yes'],
               help="Specifies whether or not plots should be generated")
            outopts.add_argument('--json', '-j', choices=['no', 'yes'],
               help="Produce JSON output files as part of climatology/diags generation") # same
            outopts.add_argument('--netcdf', '-c', choices=['no', 'yes'],
               help="Produce NetCDF output files as part of climatology/diags generation") # same
            outopts.add_argument('--xml', '-x', choices=['no', 'yes'],
               help="Produce XML output files as part of climatology/diags generation")
            outopts.add_argument('--logo', choices=['no', 'yes']) # intentionally undocumented; meant to be passed via metadiags
            outopts.add_argument("--runby", choices=['shell','meta','multi'], help="if present, states that which program is running at top level: multi (multidiags), meta (metadiags), or (default) shell (diags from the shell).  This affects output file names.")
            outopts.add_argument('--no-antialiasing', action="store_true",default = False) # intentionally undocumented; meant to be passed via metadiags
            outopts.add_argument('--table', action='store_true', help="used to get data from individual files and create the table.") # intentionally undocumented; meant to be passed via metadiags
            outopts.add_argument('--colormaps', nargs='*', help="Specify one of 3 colormaps: model, obs or diff")
            outopts.add_argument('--displayunits', nargs='*', help="Specify units for display")

        intopts = parser.add_argument_group('Internal-use primarily')
        # a few internal options not likely to be useful to anyone except metadiags
        if 'metadiags' not in progname and 'climatology' not in progname and 'metadiags.py' not in progname and 'climatology.py' not in progname:
            intopts.add_argument('--prefix',
                                 help="Specify an output filename prefix to be prepended to all file names created internally. For example --prefix myout might generate myout-PBOT_JAN_GPCP.nc, etc")
            intopts.add_argument('--postfix',
                                 help="Specify an output filename postfix to be appended to all file names created internally. For example --postfix _OBS might generate set1-JAN_OBS.nc, etc")
        if 'climatology' not in progname and 'climatology.py' not in progname:
            intopts.add_argument('--generate', '-g', choices=['no','yes'],
                                 help="Specifies whether or not climatologies should be generated")

        if 'metadiags' in progname or 'metadiags.py' in progname:
            metaopts = parser.add_argument_group('Metadiags-specific')
            metaopts.add_argument('--hostname',
                                  help="Specify the hostname of the machine hosting the Diagnostics Viewer. Requires you to have initialized your Diagnostics Viewer credentials by doing `login_viewer [server_name] --user $USERNAME.`")
            metaopts.add_argument('--dsname',
                                  help="A unique identifier for the dataset(s). Used by classic viewer to display the data.")

        if 'mpidiags' in progname or 'mpidiags.py' in progname:
            paropts = parser.add_argument_group('Parallel-specific')
            paropts.add_argument('--taskspernode',
                                 help="Specify the maximum number of tasks usable on a given node. Typically this would be set to numcores/node unless memory is an issue")
    def parseCmdLine(self):
        ### Do the work
        #args = parser.parse_args()
        import sys, pdb
        progname = sys.argv[0]
        progname = progname.split('/')[-1]
        parser = argparse.ArgumentParser( add_help=False,
                                          description="""UV-CDAT Climate Modeling Diagnostics For additional instructions, see also %s""" % help_url,
                                          usage='%(prog)s [options]',
                                          formatter_class=argparse.RawDescriptionHelpFormatter,
                                          epilog=('''\
              Examples:
              %(prog)s --model path=/path/to/a/dataset,climos=yes --obs path=/path/to/a/obs/set,climos=yes,filter='f_startswith("NCEP")' --package AMWG --coll 4 --vars Z3 --varopts 300 500
              is the same as:
              %(prog)s --path /path/to/a/dataset --climos yes --path /path/to/an/obsset --type obs --climos yes --filter 'f_startswith("NCEP")' --package AMWG --coll 4 --vars Z3 --varopts 300 500

              --model/--obs or --path can be specified multiple times.
              '''))
        self.processCmdLine(progname, parser)
        args, extras = parser.parse_known_args()
        #pdb.set_trace()
        if(args.version == 1):
            import metrics.common.utilities
            klist = metrics.common.utilities.provenance_dict().keys()
            for k in klist:
                print '%s - %s' % (k, metrics.common.utilities.provenance_dict()[k])
        #         provenance_dict()['version']

            quit()
        if(args.help == 1):
            if 'metadiags' in progname or 'metadiags.py' in progname:
                self.metadiags_help()
            elif 'climatology' in progname or 'climatology.py' in progname:
                self.climatology_help()
            else:
                self.diags_help()
            quit()
        if(args.extended_help == 1):
            parser.print_help()
            quit()


        ####
        #### This is where we start actually dealing with some options.
        ####

        # Set up the logging before anything else, so we can use the logger everywhere.
        self.processLogging(args.log_level, args.log_file)
        logsave = self._opts.get( "logging", None )   #jfp
        if logsave==None:
            self._opts["logging"] = { "level":logging.DEBUG, "file":None }
        if self._opts["logging"]["level"] < logging.INFO:
            fmt = "%(levelname)s (from %(filename)s %(lineno)d): %(message)s"
        else:
            fmt = "%(levelname)s: %(message)s"
        if "file" not in self["logging"].keys():
            self["logging"]["file"] = options_defaults["logging"]["file"]
        logging.basicConfig(level=self._opts["logging"]["level"], filename=self._opts["logging"]["file"], format=fmt)
        if logsave is None:
            del self._opts["logging"]
        else:
            self._opts["logging"] = None

        # First, check for the --list option so we don't have to do as much work if it was passed.
        if(args.list != None):
            self.listOpts(args)


        # First, print all of the provenance information regardless.
        import metrics.common.utilities
        klist = metrics.common.utilities.provenance_dict().keys()
        logger.info('BEGIN PROVENANCE INFORMATION')
        for k in klist:
            logger.info('%s - %s', k, metrics.common.utilities.provenance_dict()[k])
        logger.info('END PROVENANCE INFORMATION')

        # Generally if we've gotten this far, it means no --list was specified. If we don't have
        # at least a path, we should exit.
        #if(args.path == None and args.model == None and args.obs == None):
        #    logging.critical('Must specify a --path or one of the --model/--obs options, or the --list option')
        #    logging.critical('For help, type "diags --help".')
        #    quit()

        if args.path != None and (args.model != None or args.obs != None):
            logging.critical('Please do not combine --path and the --model/--obs methods right now')
            quit()

        ### Process dataset/obs arguments
        if args.model != None:
            self.processModel(args.model)
        if args.obs != None:
            self.processObs(args.obs)

        if(args.path != None):
            self.processPaths(args)

        if(args.cachepath != None):
            self._opts['cachepath'] = args.cachepath[0]
        try:
            cachepath = self._opts.get('cachepath','/tmp/'+getpass.getuser()+'/uvcmetrics') #jfp
            os.makedirs(cachepath)
        except OSError as e:  # usually means path already exists, but make sure:
            #jfpif not os.path.isdir(self._opts['cachepath']):
            if not os.path.isdir(cachepath):
                raise e
        if args.modelpath != None:
            self['modelpath'] = args.modelpath[0]
        if args.obspath != None:
            self['obspath'] = args.obspath[0]

        if (args.levels) != None:
            self.processLevels('levels', args.levels, extras)

        if (args.difflevels) != None:
            self.processLevels('difflevels', args.difflevels, extras)

        if args.colormaps != None:
            self.processColormaps('colormaps', args.colormaps)

        if args.displayunits != None:
            self.processDisplayunits('displayunits', args.displayunits)

        if args.uservars != None:
            self.processUservars(args.uservars)

        if "metadiags" in progname:
            if args.custom_specs is not None:
                logger.info("Using custom dict")
                if not os.path.exists(args.custom_specs):
                    raise ValueError("Error could not open custom specifications file at: %s" % args.custom_specs)
            self._opts["custom_specs"] = args.custom_specs

        # I checked; these are global and it doesn't seem to matter if you import cdms2 multiple times;
        # they are still set after you set them once in the python process.
        if(args.compress != None):
            if args.compress == 'no' or args.compress == 'False' or args.compress == 'No':
                self._opts['output']['compress'] = False
            else:
                self._opts['output']['compress'] = True

        #jfp if self._opts['output']['compress'] == False:
        try:
            compress = self._opts['output']['compress']
        except:
            compress = False #jfp
        if compress == False:
            logger.info('Disabling NetCDF compression on output files')
            cdms2.setNetcdfShuffleFlag(0)
            cdms2.setNetcdfDeflateFlag(0)
            cdms2.setNetcdfDeflateLevelFlag(0)
        else:
            logger.info('Enabling NetCDF compression on output files')
            cdms2.setNetcdfShuffleFlag(1)
            cdms2.setNetcdfDeflateFlag(1)
            cdms2.setNetcdfDeflateLevelFlag(9)

        if 'metadiags' in progname or 'metadiags.py' in progname:
            if args.hostname != None:
                self._opts['dbhost'] = args.hostname
                self._opts['do_upload'] = True
            if args.dsname != None:
                self._opts['dsname'] = args.dsname

        # Disable the UVCDAT logo in plots for users (typically metadiags) that know about this option
        if 'climatology' not in progname and 'climatology.py' not in progname:
            if args.logo != None:
                if args.logo.lower() == 'no' or args.logo == 0:
                    self._opts['output']['logo'] = False
            if args.no_antialiasing is True:
                self._opts['output']['antialiasing'] = False
            if args.table != None:
                if args.table == True:
                    self._opts['output']['table'] = True

            # A few output arguments.
            if(args.json != None):
                if(args.json.lower() == 'no' or args.json == 0):
                    self._opts['output']['json'] = False
                else:
                    self._opts['output']['json'] = True
            if(args.xml != None):
                if(args.xml.lower() == 'no' or args.xml == 0):
                    self._opts['output']['xml'] = False
                else:
                    self._opts['output']['xml'] = True
            if(args.netcdf != None):
                if(args.netcdf.lower() == 'no' or args.netcdf == 0):
                    self._opts['output']['netcdf'] = False
                else:
                    self._opts['output']['netcdf'] = True
            if(args.plots != None):
                if(args.plots.lower() == 'no' or args.plots == 0):
                    self._opts['output']['plots'] = False
                else:
                    self._opts['output']['plots'] = True
            if(args.runby != None):
                self['runby'] = args.runby

            if(args.generate != None):
                if(args.generate.lower() == 'no' or args.generate == 0):
                    self._opts['output']['climos'] = False
                else:
                    self._opts['output']['climos'] = True
            if(args.translate != 'y'):
                logger.debug(args.translate)
                logger.debug(self._opts['translate'])
                quit()
            self._opts['dryrun'] = args.dryrun
            self._opts['sbatch'] = args.sbatch
            self._opts['regrid'] = args.regrid
            if args.sbatch>0:
                self._opts["dryrun"] = True
        self._opts['verbose'] = args.verbose

        # Help create output file names
        if 'metadiags' not in progname and 'climatology' not in progname and 'climatology.py' not in progname and 'metadiags.py' not in progname:
            if(args.prefix != None):
                self._opts['output']['prefix'] = args.prefix
            if(args.postfix != None):
                self._opts['output']['postfix'] = args.postfix
        # If an output directory was specified but doesn't exist already, we can throw an error now.
        if(args.outputdir != None):
            if not os.path.isdir(args.outputdir):
                logging.critical("Output directory %s does not exist!",args.outputdir)
                quit()
            if 'output' not in self._opts:
                self._opts['output'] = {}  #jfp
            self._opts['output']['outputdir'] = args.outputdir


        if 'climatology' not in progname and 'climatology.py' not in progname:
            if(args.package != None):
                self._opts['package'] = args.package
            if(args.sets != None):
                self._opts['sets'] = args.sets
            if(args.varopts != None):
                self._opts['varopts'] = args.varopts


        # Timestart assumes a string like "months since 2000". I can't find documentation on
        # toRelativeTime() so I have no idea how to check for valid input
        # This is required for some of the land model sets I've seen
        if 'metadiags' not in progname and 'metadiags.py' not in progname:
            if(args.timestart != None):
                self._opts['reltime'] = args.timestart
            # TODO: Check against an actual list of variables from the set
            if args.vars != None:
                self._opts['vars'] = args.vars
            if(args.regions != None):
                self._opts['regions'] = args.regions

            # If --yearly is set, then we will add 'ANN' to the list of climatologies
            if(args.yearly == True):
                self._opts['times'].append('ANN')

            # If --monthly is set, we add all months to the list of climatologies
            if(args.monthly == True):
                self._opts['times'].extend(all_months)

            # If --seasonally is set, we add all the seasons to the list of climatologies
            if(args.seasonally == True):
                self._opts['times'].extend(just_seasons)

            # This allows specific individual months to be added to the list of climatologies
            if(args.months != None):
                if(args.monthly == True):
                    logger.warning("Please specify just one of --monthly or --months")
                    logger.warning('Defaulting to using all months')
                else:
                    mlist = [x for x in all_months if x in args.months]
                    self._opts['times'] = self._opts['times']+mlist

            # This allows specific individual years to be added to the list of climatologies.
            # Note: Checkign for valid input is impossible until we look at the dataset
            # This has to be special cased since typically someone will be saying
            # "Generate climatologies for seasons for years X, Y, and Z of my dataset"
            if(args.years != None):
                if(args.yearly == True):
                    logger.warning("Please specify just one of --yearly or --years")
                    logger.warning('Defaulting to using all years')
                else:
                    self._opts['years'] = args.years

            if(args.seasons != None):
                if(args.seasonally == True):
                    logger.warning("Please specify just one of --seasonally or --seasons")
                    logger.warning('Defaulting to using seasons')
                self['seasons'] = args.seasons

            self.finalizeOpts()

    def finalizeOpts( self ):
        """Clean up and finalize the options so they will be ready for use.  Most of this method
        was adapted from code formerly in parseCmdLine."""
        if 'seasons' in self.keys():
            slist = [x for x in all_seasons if x in self['seasons']]
            if 'times' in self.keys():
                self['times'] = self['times']+slist
            else:
                self['times'] = slist
            logger.debug('seasons: %s', self._opts['times'])


    def listOpts(self, args):
        print 'LIST - ', args.list
        if 'translation' in args.list or 'translations' in args.list:
            print "Default variable translations: "
            self.listTranslations()

        if 'regions' in args.list or 'region' in args.list:
            print "Available geographical regions: ", all_regions.keys()

        if 'seasons' in args.list or 'season' in args.list:
            print "Available seasons: ", all_seasons

        if 'package' in args.list or 'packages' in args.list:
            print "Listing available packages:"
            print self.all_packages.keys()

        if 'sets' in args.list or 'set' in args.list:
            if args.package == None:
                print "Please specify package before requesting available diags sets"
                quit()
            print 'Avaialble sets for package ', args.package, ':'
            sets = self.listSets(args.package)
            keys = sets.keys()
            for k in keys:
                print 'Set',k, ' - ', sets[k]

        if 'variables' in args.list or 'vars' in args.list or 'var' in args.list:
            if args.path == None and args.model == None and args.obs == None:
                logging.critical('Must provide a dataset when requesting a variable listing')
                quit()
            else:
                if args.path == None:
                    if args.model != None:
                        self.processModel(args.model)
                    if args.obs != None:
                        self.processObs(args.obs)
                else:
                    self.processPaths(args)

            self.listVariables(args.package, args.sets)

        if 'options' in args.list or 'option' in args.list:
            if args.path == None and args.model == None and args.obs == None:
                logging.critical('Must provide a dataset when requesting a variable listing')
                quit()
            else:
                if args.path == None:
                    if args.model != None:
                        self.processModel(args.model)
                    if args.obs != None:
                        self.processObs(args.obs)
                else:
                    self.processPaths(args)

            self.listVarOptions(args.package, args.sets, args.vars)
        quit()

        # Make this work in both metadiags and diags.
        if 'climatology' not in progname and 'climatology.py' not in progname:
            if(args.levels):
                self.processLevels(args.levels)

### Helper functions

options_defaults = Options( 
    model = [],
    obs = [],
    times = [],  # This is where seasonal/monthly/yearly choices end up
    package = None,
    vars = ['ALL'],
    varopts = None,
    sets = None,
    regions = [],
    uservars = [],

    reltime = None,
    cachepath = '/tmp/'+getpass.getuser()+'/uvcmetrics',
    translate = True,
    translations = {},
    levels = None,
    difflevels = None,   #levels for a difference plot
    colormaps = {'model': 'viridis', 'obs': 'viridis', 'diff': 'bl_to_darkred'},
    taskspernode = None,
    displayunits = None,
    # output pre, post, directory, absolute filename, output options:
    output = { 'compress': True,
               'json': False,
               'xml': True,
               'netcdf': True,
               'plots': True,
               'antialiasing': True,
               'climos': True,
               'outputdir': '/tmp',
               'prefix': '',
               'postfix': '',
               'logo': True,
               'table': False },
    logging = { 'level': logging.ERROR,
                'file' : None },
    dbhost = "https://diags-viewer.llnl.gov",
    dsname = None,
    do_upload = False )

### make_ft_dict - provides an easily parsed dictionary of the climos/raws for a given set of datasets
def make_ft_dict(models):
    model_dict = {}
    index = 0

    for i in range(len(models)):
        key = 'model%s' % index
        if models[i]._name == None: # just add it if it has no name
            model_dict[key] = {}
            model_dict[key]['name'] = None
            if models[i]._climos != 'no': # Assume they are climos unless told otherwise
                model_dict[key]['climos'] = models[i]
                model_dict[key]['raw'] = None
            else:
                model_dict[key]['climos'] = None
                model_dict[key]['raw'] = models[i]
            index = index + 1
        else: # it has a name. have we seen it already?
            name = models[i]._name
            model_names = [model_dict[x]['name'] for x in model_dict.keys()]
            if name in model_names: # we've seen it before
                logger.warning('Found %s in model_names weve seen already.', name)
                for j in model_dict.keys():
                    if model_dict[j]['name'] == name:
                        if models[i]._climos != 'no':
                            model_dict[j]['climos'] = models[i]
                        else:
                            model_dict[j]['raw'] = models[i]
            else:
                model_dict[key] = {}
                model_dict[key]['name'] = name
                if models[i]._climos != 'no':
                    model_dict[key]['climos'] = models[i]
                    model_dict[key]['raw'] = None
                else:
                    model_dict[key]['raw'] = models[i]
                    model_dict[key]['climos'] = None
                index = index +1

    return model_dict


if __name__ == '__main__':

    o = Options()
    o.parseCmdLine()
    from metrics.fileio.findfiles import *
    print o._opts
    modelfts = []
    for i in range(len(o['model'])):
        modelfts.append(path2filetable(o, modelid=i))
    model_dict = make_ft_dict(modelfts)
    for i in model_dict.keys():
        print 'key: %s - %s' % (i, model_dict[i])
    print dir(modelfts[0])

    print modelfts[0].root_dir()
