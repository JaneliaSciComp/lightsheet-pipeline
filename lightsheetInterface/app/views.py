import requests, json, os, math, datetime, bson, re, subprocess, ipdb
from flask import render_template, request, abort
from pymongo import MongoClient
from collections import OrderedDict
from datetime import datetime
from pprint import pprint
from app import app
from app.settings import Settings
from app.utils import *

settings = Settings()
# Prefix for all default pipeline step json file names
defaultFileBase = None
if hasattr(settings, 'defaultFileBase'):
  defaultFileBase = settings.defaultFileBase

# Location to store json files
outputDirectoryBase = None
if hasattr(settings, 'outputDirectoryBase'):
  outputDirectoryBase = settings.outputDirectoryBase
global_error = None

# Mongo client
client = MongoClient(settings.mongo)
# lightsheetDB is the database containing lightsheet job information and parameters
lightsheetDB = client.lightsheet

app.route('/register', methods=['GET', 'POST'])


def register():
  form = RegistrationForm(request.form)
  if request.method == 'POST' and form.validate():
    user = User(form.username.data, form.email.data,
                form.password.data)
    db_session.add(user)
    flash('Thanks for registering')
    return redirect(url_for('login'))
  return render_template('register.html',
                         form=form,
                         version=getAppVersion(app.root_path))


@app.route('/login')
def login():
  return render_template('login.html',
                         logged_in=False,
                         version=getAppVersion(app.root_path))


@app.route('/submit', methods=['GET', 'POST'])
def submit():
  if request.method == 'POST':
    keys = request.form.keys()
    for k in iter(keys):
      print(k)
  return 'form submitted'


@app.route('/job/<job_id>', methods=['GET', 'POST'])
def load_job(job_id):
  config = buildConfigObject()
  if job_id == 'favicon.ico':
    job_id = None

  pipelineSteps = {}
  formData = None
  countJobs = 0
  # go through all steps and find those, which are used by the current job
  for step in config['steps']:
    currentStep = step.name
    configData = getConfigurationsFromDB(job_id, client, currentStep)
    print(configData)
    if configData != None and job_id != None:
      # If loading previous run parameters for specific step, then it should be checked and editable
      editState = 'enabled'
      checkboxState = 'checked'
      countJobs += 1
      forms = parseJsonData(configData)
      # Pipeline steps is passed to index.html for formatting the html based
      pipelineSteps[currentStep] = {
        'stepName': step.name,
        'stepDescription': step.description,
        'inputJson': None,
        'state': editState,
        'checkboxState': checkboxState,
        'forms': forms
      }
    if request.method == 'POST':
      # If a job is submitted (POST request) then we have to save parameters to json files and to a database and submit the job
      # lightsheetDB is the database containing lightsheet job information and parameters
      numSteps = 0
      allSelectedStepNames = ""
      allSelectedTimePoints = ""
      stepParameters = []

      userDefinedJobName = []
      for currentStep in config['steps']:
        text = request.form.get(currentStep)  # will be none if checkbox is not checked
        if text is not None:
          if numSteps == 0:
            # Create new document in jobs collection in lightsheet database and create json output directory
            newId = lightsheetDB.jobs.insert_one({"steps": {}}).inserted_id
            outputDirectory = outputDirectoryBase + str(newId) + "/"
            postBody = {"processingLocation": "LSF_JAVA",
                        "args": ["-configDirectory", outputDirectory],
                        "resources": {"gridAccountId": "lightsheet"}
                        # ,"queueId":"jacs-dev"
                        }
            os.mkdir(outputDirectory)
          # Write json files
          fileName = str(numSteps) + "_" + currentStep + ".json"
          fh = open(outputDirectory + fileName, "w")
          fh.write(text)
          fh.close()
          # Store step parameters and step names/times to use as arguments for the post
          jsonifiedText = json.loads(text, object_pairs_hook=OrderedDict)
          stepParameters.append({"stepName": currentStep, "parameters": jsonifiedText})
          numTimePoints = math.ceil(1 + (jsonifiedText["timepoints"]["end"] - jsonifiedText["timepoints"]["start"]) /
                                    jsonifiedText["timepoints"]["every"])
          allSelectedStepNames = allSelectedStepNames + currentStep + ","
          allSelectedTimePoints = allSelectedTimePoints + str(numTimePoints) + ", "
          numSteps += 1

      if numSteps > 0:
        # Finish preparing the post body
        allSelectedStepNames = allSelectedStepNames[0:-1]
        allSelectedTimePoints = allSelectedTimePoints[0:-2]
        postBody["args"].extend(("-allSelectedStepNames", allSelectedStepNames))
        postBody["args"].extend(("-allSelectedTimePoints", allSelectedTimePoints))

        # Post to JACS
        requestOutput = requests.post(settings.devOrProductionJACS + '/async-services/lightsheetProcessing',
                                      headers=getHeaders(),
                                      data=json.dumps(postBody))

        requestOutputJsonified = requestOutput.json()
        # Store information about the job in the lightsheet database
        currentLightsheetCommit = subprocess.check_output(
          ['git', '--git-dir', settings.pipelineGit, 'rev-parse', 'HEAD']).strip().decode("utf-8")
        if not userDefinedJobName:
          userDefinedJobName = requestOutputJsonified["_id"]

        lightsheetDB.jobs.update_one({"_id": newId},
                                     {"$set": {"jacs_id": requestOutputJsonified["_id"], "jobName": userDefinedJobName,
                                               "lightsheetCommit": currentLightsheetCommit,
                                               "jsonDirectory": outputDirectory,
                                               "selectedStepNames": allSelectedStepNames, "steps": stepParameters}})


        # Give the user the ability to define local jobs, for development purposes for instance
        # if hasattr(settings, 'localJobs') and len(settings.localJobs) > 0:
        #     for job in settings.localJobs:
        # jobData = loadJobDataFromLocal(job)
        # formData = parseJsonData(jobData)
        # parentServiceData.append(jobData)

  # Return index.html with pipelineSteps and serviceData
  return render_template('index.html',
                         pipelineSteps=pipelineSteps,
                         logged_in=True,
                         config=config,
                         version=getAppVersion(app.root_path),
                         jobIndex=job_id)


@app.route('/', methods=['GET'])
def index():
  lightsheetDB_id = request.args.get('lightsheetDB_id')
  config = buildConfigObject()
  parentJobInfo = getJobInfoFromDB(lightsheetDB, lightsheetDB_id,"parent")

  # Return index.html with pipelineSteps and serviceData
  return render_template('index.html',
                         steps=config['steps'],
                         parentJobInfo = parentJobInfo,
                         logged_in=True,
                         config=config,
                         version=getAppVersion(app.root_path))


@app.route('/job_status/', methods=['GET'])
def job_status():
  jobIndex = request.args.get('jacsServiceIndex')
  # Mongo client
  client = MongoClient(settings.mongo)
  # lightsheetDB is the database containing lightsheet job information and parameters
  lightsheetDB = client.lightsheet

  # For now, get information from jacs database directly to monitor parent and child job statuses
  parentServiceData = getParentServiceDataFromJACS(lightsheetDB, jobIndex)
  childSummarizedStatuses = []

  if jobIndex is not None:
    jobIndex = int(jobIndex)

    # If a specific parent job is selected, find all the child job status information and store the step name, status, start time, endtime and elapsedTime
    childJobStatuses = getChildServiceDataFromJACS(parentServiceData[jobIndex]["_id"])
    steps = parentServiceData[jobIndex]["args"][3].split(",")
    for i in range(0, len(steps)):
      if i <= len(childJobStatuses) - 1:
        childSummarizedStatuses.append({"step": steps[i], "status": childJobStatuses[i]["state"],
                                        "startTime": str(childJobStatuses[i]["creationDate"]),
                                        "endTime": str(childJobStatuses[i]["modificationDate"]),
                                        "elapsedTime": str(
                                          childJobStatuses[i]["modificationDate"] - childJobStatuses[i][
                                            "creationDate"])})
        if childJobStatuses[i]["state"] == "RUNNING":
          childSummarizedStatuses[i]["elapsedTime"] = str(
            datetime.now(utils.eastern) - childJobStatuses[i]["creationDate"])
      else:
        childSummarizedStatuses.append(
          {"step": steps[i], "status": "NOT YET QUEUED", "startTime": "N/A", "endTime": "N/A", "elapsedTime": "N/A"})

  # Return job_status.html which takes in parentServiceData and childSummarizedStatuses
  return render_template('job_status.html',
                         parentServiceData=parentServiceData,
                         childSummarizedStatuses=childSummarizedStatuses,
                         logged_in=True,
                         version=getAppVersion(app.root_path))


@app.route('/config/<_id>', methods=['GET'])
def config(_id):
  stepName = request.args.get('stepName')
  output = getConfigurationsFromDB(_id, client, stepName)
  if output == 404:
    abort(404)
  else:
    return jsonify(output)


@app.route('/search')
def search():
  return render_template('search.html',
                         logged_in=True,
                         version=getAppVersion(app.root_path))

# @app.errorhandler(404)
# def error_page(error):
#     err = 'There was an error using that page. Please make sure, you are connected to the internal network of '
#     err += 'Janelia and check with SciComp, if the application is configured correctly.';
#     if global_error != None:
#         err += '\n' + global_error
#     return render_template('error.html', err=err), 404
