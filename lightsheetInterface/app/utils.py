import numpy, datetime, glob, scipy, re, json, requests, os, ipdb, re, math
import matplotlib
matplotlib.use('agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from wtforms import *
from multiprocessing import Pool
from pprint import pprint
from scipy import misc
from datetime import datetime
from pytz import timezone
from bson.objectid import ObjectId
from pymongo.errors import ServerSelectionTimeoutError
from app.models import AppConfig, Step, Parameter
from app.settings import Settings

settings = Settings()

# collect the information about existing job used by the job_status page
def getJobInfoFromDB(lightsheetDB, _id=None, parentOrChild="parent", getParameters=False):
  if _id:
    _id = ObjectId(_id)
    if parentOrChild=="parent":
      parentJobInfo = list(lightsheetDB.jobs.find({},{"steps":0}))
      for currentJobInfo in parentJobInfo:
        currentJobInfo.update({"selected":""})
        if currentJobInfo["_id"]==_id:
          currentJobInfo.update({"selected":"selected"})
      return parentJobInfo
    else:
      if getParameters:
        return list(lightsheetDB.jobs.find({"_id":_id}))
      else:
        return list(lightsheetDB.jobs.find({"_id":_id},{"steps.parameters":0}))
  else:
    return list(lightsheetDB.jobs.find({},{"steps":0}))

# build result object of existing job information
def mapJobsToDict(x):
  result = {}
  if '_id' in x:
    result['id'] = str(x['_id']) if str(x['_id']) is not None else ''
  if 'jobName' in x:
    result['jobName'] = x['jobName'] if x['jobName'] is not None else ''
  if 'creationDate' in x:
    result['creationDate'] = x['creationDate'] if x['creationDate'] is not None else ''
  if 'selectedStepNames' in x:
    result['selectedStepNames'] = x['selectedStepNames'] if x['selectedStepNames'] is not None else ''
  if 'state' in x:
    result['state'] = x['state'] if x['state'] is not None else ''
  if 'jacs_id' in x:
    result['jacs_id'] = x['jacs_id'] if x['jacs_id'] is not None else ''
  return result;

# get job information used by jquery datatable
def allJobsInJSON(lightsheetDB):
  parentJobInfo = lightsheetDB.jobs.find({}, {"steps": 0})
  return list(map(mapJobsToDict, parentJobInfo))

# build object with meta information about parameters from the admin interface
def getParameters(parameter):
  frequent = {}
  sometimes = {}
  rare = {}
  for param in parameter:
    if param.number1 != None:
      param.type = 'Number'
      if param.number2 == None:
        param.count = '1'
      elif param.number3 == None:
        param.count = '2'
      else:
        param.count = '3'
    else:
      param.type = 'Text'
      param.count = '1'

    if param.frequency == 'F':
      frequent[param.name] = param
    elif param.frequency == 'S':
      sometimes[param.name] = param
    elif param.frequency == 'R':
      rare[param.name] = param

  result = {'frequent': frequent, 'sometimes': sometimes, 'rare': rare}
  return result

# build object with information about steps and parameters about admin interface
def buildConfigObject():
  try:
    steps = Step.objects.all().order_by('order')
    p = Parameter.objects.all()
    paramDict = getParameters(p)
    config = {'steps': steps, 'parameterDictionary': paramDict}
  except ServerSelectionTimeoutError:
    return 404
  return config

# Header for post request
def getHeaders(forQuery=False):
  if forQuery:
    return {'content-type': 'application/json', 'USERNAME': settings.username}
  else:
    return {'content-type': 'application/json', 'USERNAME': settings.username, 'RUNASUSER': 'lightsheet'}

# Timezone for timings
eastern = timezone('US/Eastern')
UTC = timezone('UTC')

def getJobInfoFromDB(lightsheetDB, _id=None, parentOrChild="parent", getParameters=False):
  if _id:
    _id = ObjectId(_id)
    if parentOrChild=="parent":
      parentJobInfo = list(lightsheetDB.jobs.find({},{"steps":0}))
      for currentJobInfo in parentJobInfo:
        currentJobInfo.update({"selected":""})
        if currentJobInfo["_id"]==_id:
          currentJobInfo.update({"selected":"selected"})
      return parentJobInfo
    else:
      if getParameters:
        return list(lightsheetDB.jobs.find({"_id":_id}))
      else:
        return list(lightsheetDB.jobs.find({"_id":_id},{"steps.parameters":0}))
  else:
    return list(lightsheetDB.jobs.find({},{"steps":0}))

# get step information about existing jobs from db
def getJobStepData(_id, mongoClient):
  result = getConfigurationsFromDB(_id, mongoClient, stepName=None)
  if result != None and result != 404 and len(result) > 0 and 'steps' in result[0]:
    return result[0]['steps']
  return None

# get the job parameter information from db
def getConfigurationsFromDB2(_id, mongoClient, stepName=None):
  result = None
  lightsheetDB = mongoClient.lightsheet
  if _id == "templateConfigurations":
    jobSteps = list(lightsheetDB.templateConfigurations.find({}, {'_id': 0, 'steps': 1}))
  else:
    jobSteps = list(lightsheetDB.jobs.find({'_id': ObjectId(_id)}, {'_id': 0, 'steps': 1}))

  if jobSteps:
    jobStepsList = jobSteps[0]["steps"]
    if stepName is not None:
      stepDictionary = next((dictionary for dictionary in jobStepsList if dictionary["name"] == stepName), None)
      if stepDictionary is not None:
        return stepDictionary["parameters"]
  return None

# get the job parameter information from db
def getConfigurationsFromDB(_id, client, stepName=None):
  lightsheetDB = client.lightsheet
  if stepName:
    if stepName=='getArgumentsToRunJob':
      output = getArgumentsToRunJob(lightsheetDB, _id)
    else:
      output = list(lightsheetDB.jobs.find({'_id':ObjectId(_id),'steps.name':stepName},{'_id':0,"steps.$.parameters":1}))
      if output:
        output=output[0]["steps"][0]["parameters"]
  else:
      output = list(lightsheetDB.jobs.find({'_id':ObjectId(_id)},{'_id':0,'steps':1}))
  if output:
    print(output)
    return output
  else:
    return 404

# get the job parameter information from db
def getArgumentsToRunJob(lightsheetDB, _id):
  currentJobSteps = lightsheetDB.jobs.find({'_id':ObjectId(_id)},{'_id':0,'steps.name':1,'steps.parameters.timepoints':1})
  output={"currentJACSJobStepNames":'', "currentJACSJobTimePoints":'','configOutputPath':''}
  for step in currentJobSteps[0]["steps"]:
    output["currentJACSJobStepNames"] = output["currentJACSJobStepNames"]+step["name"]+','
    timepoints = step["parameters"]["timepoints"];
    timepointStart = timepoints["start"]
    timepointEvery = timepoints["every"]
    timepointEnd = timepoints["end"]
    output["currentJACSJobTimePoints"] = output["currentJACSJobTimePoints"] +str(int(1+math.ceil(timepointEnd-timepointStart)/timepointEvery))+',' 
  if output["currentJACSJobStepNames"] and output["currentJACSJobTimePoints"]:
    output["currentJACSJobStepNames"]=output["currentJACSJobStepNames"][:-1]
    output["currentJACSJobTimePoints"]= output["currentJACSJobTimePoints"][:-1]
    configOutputPath = lightsheetDB.jobs.find({'_id':ObjectId(_id)},{'_id':0,'configOutputPath':1})
    if configOutputPath[0]:
      output["configOutputPath"]=configOutputPath[0];
    return output
  else:
    return 404

# get latest status information about jobs from db
def updateDBStatesAndTimes(lightsheetDB):
  allJobInfoFromDB = list(lightsheetDB.jobs.find())
  for parentJobInfoFromDB in allJobInfoFromDB:
    if 'jacs_id' in parentJobInfoFromDB: # TODO handle case, when jacs_id is missing
      if parentJobInfoFromDB["state"] not in ['CANCELED', 'TIMEOUT', 'ERROR', 'SUCCESSFUL']:
        parentJobInfoFromJACS = requests.get(settings.devOrProductionJACS+'/services/',
                                                    params={'service-id':  parentJobInfoFromDB["jacs_id"]},
                                                    headers=getHeaders(True)).json()
        if parentJobInfoFromJACS and len(parentJobInfoFromJACS["resultList"]) > 0:
          parentJobInfoFromJACS = parentJobInfoFromJACS["resultList"][0]
          lightsheetDB.jobs.update_one({"_id":parentJobInfoFromDB["_id"]},
                                       {"$set": {"state":parentJobInfoFromJACS["state"] }})
          allChildJobInfoFromJACS = requests.get(settings.devOrProductionJACS+'/services/',
                                              params={'parent-id': parentJobInfoFromDB["jacs_id"]},
                                              headers=getHeaders(True)).json()
          allChildJobInfoFromJACS = allChildJobInfoFromJACS["resultList"]
          if allChildJobInfoFromJACS:
            for currentChildJobInfoFromDB in parentJobInfoFromDB["steps"]:
              if "state" in currentChildJobInfoFromDB and currentChildJobInfoFromDB["state"] not in ['CANCELED', 'TIMEOUT', 'ERROR', 'SUCCESSFUL']: #need to update step
                currentChildJobInfoFromJACS = next((step for step in allChildJobInfoFromJACS if step["args"][1] == currentChildJobInfoFromDB["name"]),None)
                if currentChildJobInfoFromJACS:
                  creationTime = convertJACStime(currentChildJobInfoFromJACS["processStartTime"])
                  outputPath = "N/A"
                  if "outputPath" in currentChildJobInfoFromJACS:
                    outputPath = currentChildJobInfoFromJACS["outputPath"][:-11]

                  lightsheetDB.jobs.update_one({"_id":parentJobInfoFromDB["_id"],"steps.name": currentChildJobInfoFromDB["name"]},
                                               {"$set": {"steps.$.state":currentChildJobInfoFromJACS["state"],
                                                         "steps.$.creationTime": creationTime.strftime("%Y-%m-%d %H:%M:%S"),
                                                         "steps.$.elapsedTime":str(datetime.now(eastern)-creationTime),
                                                         "steps.$.logAndErrorPath":outputPath
                                                       }})

                  if currentChildJobInfoFromJACS["state"] in ['CANCELED', 'TIMEOUT', 'ERROR', 'SUCCESSFUL']:
                    endTime = convertJACStime(currentChildJobInfoFromJACS["modificationDate"])
                    lightsheetDB.jobs.update_one({"_id":parentJobInfoFromDB["_id"],"steps.name": currentChildJobInfoFromDB["name"]},
                                                 {"$set": {"steps.$.endTime": endTime.strftime("%Y-%m-%d %H:%M:%S"),
                                                           "steps.$.elapsedTime": str(endTime-creationTime)
                                                         }})
  
def convertJACStime(t):
   t=datetime.strptime(t[:-9], '%Y-%m-%dT%H:%M:%S')
   t=UTC.localize(t).astimezone(eastern)
   return t

def convertArrayFieldValue(stringValue):
  stringValue = stringValue.replace("{","") #remove cell formatting
  stringValue = stringValue.replace("}","")
  stringValue = stringValue.replace(" ",",") #replace commas with spaces
  #stringValue = ' '.join(stringValue.split()) #make sure everything is singlespaced
  #stringValue = stringValue.replace(" ",",") #replace spaces by commas
  stringValue = re.sub(',,+' , ',', stringValue) #replace two or more commas with single comma
  #lots of substitutions to have it make sense. First get rid of extra commas
  #Then get rid of semicolon-comma pairs
  #Then make sure arrays are separated properly
  #Finally add brackets to the beginning/end if necessary
  stringValue = re.sub('\[,' , '[', stringValue) 
  stringValue = re.sub(',\]' , ']', stringValue)
  stringValue = re.sub(';,' , ';', stringValue)
  stringValue = re.sub(',;' , ';', stringValue)
  stringValue = re.sub('\];\[' , '],[', stringValue)
  stringValue = re.sub(';', '],[', stringValue)
  if '],[' in stringValue:
    stringValue = "[" + stringValue + "]"
  return 


def convertEpochTime(v):
  if type(v) is str:
    return v
  else:
    return datetime.fromtimestamp(int(v) / 1000, eastern)


def insertImage(camera, channel, plane):
  imagePath = path + 'SPC' + specimenString + '_TM' + timepointString + '_ANG000_CM' + camera + '_CHN' + channel.zfill(
    2) + '_PH0_PLN' + str(plane).zfill(4) + '.tif'
  return misc.imread(imagePath)


def generateThumbnailImages(path, timepoint, specimen, cameras, channels, specimenString, timepointString):
  # path = sys.argv[1]
  # timepoint = sys.argv[2]
  # specimen = sys.argv[3]
  # cameras = sys.argv[4].split(',')
  # channels = sys.argv[5].split(',')
  # specimenString = specimen.zfill(2)
  # timepointString = timepoint.zfill(5)
  # path = path+'/SPM' + specimenString + '/TM' + timepointString + '/ANG000/'

  pool = Pool(processes=32)
  numberOfChannels = len(channels)
  numberOfCameras = len(cameras)
  # fig, ax = plt.subplots(nrows = numberOfChannels, ncols = 2*numberOfCameras)#, figsize=(16,8))
  fig = plt.figure();
  fig.set_size_inches(16, 8)
  outer = gridspec.GridSpec(numberOfChannels, numberOfCameras, wspace=0.3, hspace=0.3)

  for channelCounter, channel in enumerate(channels):
    for cameraCounter, camera in enumerate(cameras):
      inner = gridspec.GridSpecFromSubplotSpec(1, 2, subplot_spec=outer[cameraCounter, channelCounter], wspace=0.1,
                                               hspace=0.1)
      newList = [(camera, channel, 0)]
      numberOfPlanes = len(glob.glob1(path, '*CM' + camera + '_CHN' + channel.zfill(2) + '*'))
      for plane in range(1, numberOfPlanes):
        newList.append((camera, channel, plane))

      images = pool.starmap(insertImage, newList)
      images = numpy.asarray(images).transpose(1, 2, 0)
      xy = numpy.amax(images, axis=2)
      xz = numpy.amax(images, axis=1)
      ax1 = plt.Subplot(fig, inner[0])
      ax1.imshow(xy, cmap='gray')
      fig.add_subplot(ax1)
      ax1.axis('auto')
      ax2 = plt.Subplot(fig, inner[1])
      ax2.imshow(xz, cmap='gray')
      fig.add_subplot(ax2)
      ax2.axis('auto')
      ax2.get_yaxis().set_visible(False)
      # ax1.get_shared_y_axes().join(ax1, ax2)
      baseString = 'CM' + camera + '_CHN' + channel.zfill(2)
      ax1.set_title(baseString + ' xy')  # , fontsize=12)
      ax2.set_title(baseString + ' xz')  # , fontsize=12)

  fig.savefig(url_for('static', filename='img/test.jpg'))
  pool.close()


def getAppVersion(path):
  mpath = path.split('/')
  result = '/'.join(mpath[0:(len(mpath) - 1)]) + '/package.json'
  with open(result) as package_data:
    data = json.load(package_data)
    package_data.close()
    return data['version']