'''
Module containing the functions necessary to interact with the wma.
Credit and less than optimal code has to be spreaded among lots of people.
'''
import os
import urllib
import httplib
import imp
import sys
import pprint
import time

try:
  from PSetTweaks.WMTweak import makeTweak
  from WMCore.Cache.WMConfigCache import ConfigCache
except:
  print "Probably no WMClient was set up. Trying to proceed anyway..."
#-------------------------------------------------------------------------------


#DBS_URL = "http://cmsdbsprod.cern.ch/cms_dbs_prod_global/servlet/DBSServlet"
DBS_URL = "https://cmsweb.cern.ch/dbs/prod/global/DBSReader"
PHEDEX_ADDR = 'https://cmsweb.cern.ch/phedex/datasvc/json/prod/blockreplicas?dataset=%s*'

DATABASE_NAME = 'reqmgr_config_cache'
COUCH_DB_ADDRESS = 'https://cmsweb.cern.ch/couchdb'
WMAGENT_URL = 'cmsweb.cern.ch'
DBS3_URL = "/dbs/prod/global/DBSReader/"

def testbed(to_url):
  global COUCH_DB_ADDRESS
  global WMAGENT_URL
  global DBS3_URL
  WMAGENT_URL = to_url
  #WMAGENT_URL = 'cmsweb-testbed.cern.ch'
  #WMAGENT_URL = 'sryu-dev01.cern.ch'
  COUCH_DB_ADDRESS = 'https://%s/couchdb'%( WMAGENT_URL )
  DBS3_URL = "/dbs/int/global/DBSReader/"

#-------------------------------------------------------------------------------

def generic_get(base_url, query):
    headers  =  {"Content-type": "application/json"}
    conn  =  httplib.HTTPSConnection(base_url, cert_file = os.getenv('X509_USER_PROXY'), key_file = os.getenv('X509_USER_PROXY'))
    conn.request("GET", query.replace("#", "%23"))
    #print "getting",base_url,query,"..."
    response = conn.getresponse()
    
    if response.status != 200:
        print "Problems quering DBS3 RESTAPI: %s" %(base_url+query.replace("#", "%23"))
        data = None
    else:
        data = response.read()
        #print "...got",data
    return data

#-------------------------------------------------------------------------------

def __check_GT(gt):
    if not gt.endswith("::All"):
        raise Exception,"It seemslike the name of the GT '%s' has a typo in it!" %gt

def __check_input_dataset(dataset):
    if dataset and dataset.count('/')!=3:
      raise Exception ("Malformed dataset name %s!" %dataset)

def __check_request_params(params):
    if params.has_key('GlobalTag'):
      __check_GT(params['GlobalTag'])
    for inputdataset in ('MCPileup','DataPileup','InputDataset'):
        if params.has_key(inputdataset):
            __check_input_dataset(params[inputdataset])


#-------------------------------------------------------------------------------


def approveRequest(url,workflow,encodeDict=False):
    params = {"requestName": workflow,
              "status": "assignment-approved"}
    encodedParams = urllib.urlencode(params)
    headers  =  {"Content-type": "application/x-www-form-urlencoded",
                 "Accept": "text/plain"}

    conn  =  httplib.HTTPSConnection(url, cert_file = os.getenv('X509_USER_PROXY'), key_file = os.getenv('X509_USER_PROXY'))
    conn.request("PUT",  "/reqmgr/reqMgr/request", encodedParams, headers)
    response = conn.getresponse()
    if response.status != 200:
        print 'could not approve request with following parameters:'
        for item in params.keys():
            print item + ": " + str(params[item])
        print 'Response from http call:'
        print 'Status:',response.status,'Reason:',response.reason
        print 'Explanation:'
        data = response.read()
        print data
        print "Exiting!"
        sys.exit(1)
    conn.close()
    print 'Approved workflow:',workflow
    return
    
#-------------------------------------------------------------------------------

def __loadConfig(configPath):
    """
    _loadConfig_

    Import a config.
    """
    print "Importing the config, this may take a while...",
    sys.stdout.flush()
    cfgBaseName = os.path.basename(configPath).replace(".py", "")
    cfgDirName = os.path.dirname(configPath)
    modPath = imp.find_module(cfgBaseName, [cfgDirName])
    loadedConfig = imp.load_module(cfgBaseName, modPath[0],modPath[1], modPath[2])

    print "done."
    return loadedConfig
    
#-------------------------------------------------------------------------------    
# DP leave this untouched even if less than optimal!
def makeRequest(url,params,encodeDict=False):

    __check_request_params(params)
    for (k,v) in params.items():
      if type(v) ==dict:
        encodeDict=True
        print "Re-encoding for nested dicts"
        break
      
    if encodeDict:
        import json
        jsonEncodedParams = {}
        for paramKey in params.keys():
            jsonEncodedParams[paramKey] = json.dumps(params[paramKey])
        encodedParams = urllib.urlencode(jsonEncodedParams, False)
    else:
        encodedParams = urllib.urlencode(params)

    headers  =  {"Content-type": "application/x-www-form-urlencoded",
                 "Accept": "text/plain"}

    conn  =  httplib.HTTPSConnection(url, cert_file = os.getenv('X509_USER_PROXY'), key_file = os.getenv('X509_USER_PROXY'))
    conn.request("POST",  "/reqmgr/create/makeSchema", encodedParams, headers)
    response = conn.getresponse()
    data = response.read()
    if response.status != 303:
        print 'could not post request with following parameters:'
        #pprint.pprint( params )
        #print
        for item in params.keys():
            print item + ": " + str(params[item])
        print 'Response from http call:'
        print 'Status:',response.status,'Reason:',response.reason
        print 'Explanation:'
        print data
        print "Exiting!"
        sys.exit(1)
    workflow=data.split("'")[1].split('/')[-1]
    print 'Injected workflow:',workflow
    conn.close()
    return workflow

#-------------------------------------------------------------------------------

def upload_to_couch(cfg_name, section_name,user_name,group_name,test_mode=False,url=None):
  if test_mode:
    return "00000000000000000"
      
  if not os.path.exists(cfg_name):
    raise RuntimeError( "Error: Can't locate config file %s." %cfg_name)

  # create a file with the ID inside to avoid multiple injections
  oldID=cfg_name+'.couchID'
  #print oldID
  #print 
  if os.path.exists(oldID):
      f=open(oldID)
      the_id=f.readline().replace('\n','')
      f.close()
      print cfg_name,'already uploaded with ID',the_id,'from',oldID
      return the_id

  try:
    loadedConfig = __loadConfig(cfg_name)
  except:
    #just try again !!
    time.sleep(2)
    loadedConfig = __loadConfig(cfg_name)
    
  where=COUCH_DB_ADDRESS
  if url:      where=url
  configCache = ConfigCache(where, DATABASE_NAME)
  configCache.createUserGroup(group_name, user_name)
  configCache.addConfig(cfg_name)
  configCache.setPSetTweaks(makeTweak(loadedConfig.process).jsondictionary())
  configCache.setLabel(section_name)
  configCache.setDescription(section_name)
  configCache.save()
  
  print "Added file to the config cache:"
  print "  DocID:    %s" % configCache.document["_id"]
  print "  Revision: %s" % configCache.document["_rev"]
  
  f=open(oldID,"w")
  f.write(configCache.document["_id"])
  f.close()
  return configCache.document["_id"]
  
#-------------------------------------------------------------------------------  
  

def time_per_events(campaign):
  ### ad-hoc method until something better comes up to define the time per event in injection time
  addHoc={
    'Summer12_DR53X' : 17.5,
    'Summer12_DR52X' :  20.00,
    'Fall11_R1' :   5.00,
    'Fall11_R2' :  10.00,
    'Fall11_R4' :   7.00,
    'UpgradeL1TDR_DR6X' : 40.00,
    'UpgradePhase2BE_2013_DR61SLHCx' : 90,
    'UpgradePhase2LB4PS_2013_DR61SLHCx' : 90,
    'UpgradePhase2LB6PS_2013_DR61SLHCx' : 90,
    }

  if campaign in addHoc:
    return addHoc[campaign]
  else:
    return None
