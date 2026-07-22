# fishingSuitability.py
#
# Author: Dushyanthi Rajakumar
# Unity ID: drajaku
# Purpose: Identify and rank the top 10 public fresh water fishing locations in North Carolina
#          based on water quality suitability, distance from a user-provided zip code,
#          and optional fish consumption safety criteria.
#
# Procedure Summary:
#  * accept all inputs through arcgis pro script tool gui or pycharm defaults.
#  * validate all input layers and copy shapefiles to scratch gdb to avoid
#      field name truncation during spatial operations.
#  * inspect all layer schemas and confirm all scoring fields exist.
#  * compute the centroid of the matching zip code polygon.
#  * reproject attains lines to match fishing sites coordinate system.
#  * spatially link each fishing access point to the nearest attains line
#      feature using closest spatial join.
#  * create a single output feature class with water quality attributes
#      joined to each fishing point.
#  * score each fishing location using water quality fields via the
#      fishingLocation class computeScore method.
#  * calculate distance from each site to the user zip code centroid.
#  * rank all locations by score then distance and return the top 10.
#  * add top 10 results to arcgis pro map with meaningful symbology.
#  * capture screenshots and generate an html report with results.
#
# Usage    : fishing_tool.py
#            all parameters have defaults and are optional.
#            coordinate_system should be provided as a wkid integer
#                    e.g. 2264 for NAD 1983 NC State Plane Feet
#                    e.g. 4326 for WGS 1984
#            provide sys.argv arguments only to override the defaults.
#
# Example input:
"""
     C:/fishing_suitability/data/public_fishing.shp
     C:/fishing_suitability/data/zip_poly.shp
     C:/fishing_suitability/data/water_quality.gdb
     27607
     2264
     true
"""


import arcpy
import os
import sys

class FishingLocation:
    """represents a single public fishing access point with its
    water quality attributes, suitability score, and distance
    from the user zip code centroid.

    methods:

    computeScore(includeFishSafety)
    setDistance(zipCentroid)
    toDict()"""

    def __init__(self, name, fid, geometry, wqFields):
        """initialize a fishing location with its attributes."""
        self.name     = name
        self.fid      = fid
        self.geometry = geometry
        self.wqFields = wqFields
        self.score    = 0
        self.distance = 0
        self.rank     = None

    def computeScore(self, includeFishSafety=False):
        """evaluate water quality fields and compute suitability score.

        starts at 125.
        basket 1 : binary fields(Y/N) - isimpaired, on303dlist
        basket 2 : cause/meeting criteria fields
        basket 3 : fully supporting/not supporting fields
        null and insufficient information treated as neutral.
        floor at 0 - score cannot go negative."""

        score = 125

        # ---binary y/n fields---
        # isimpaired
        if self.wqFields.get("isimpaired") == "Y":
            score = score - 25

        # on303dlist - if the waterbody is specifically listed on the EPA 303(d) list
        if self.wqFields.get("on303dlist") == "Y":
            score = score - 15

        # ---cause / meeting criteria fields---
        # each field has a specific penalty for cause
        # and a small bonus for meeting criteria
        # null and insufficient information = no change
        causeFields = {
            "oxygen_depletion": 10,
            "pathogens"       : 20,
            "nutrients"       : 10,
            "turbidity"       : 10
        }

        for field, penalty in causeFields.items():
            value = self.wqFields.get(field)
            if value == "Cause":
                score = score - penalty
            elif value == "Meeting Criteria":
                score = score + 5

        # ---fully supporting / not supporting fields---
        # each field has a specific penalty for not supporting
        # and a bonus for fully supporting
        # null and insufficient information = no change
        supportFields = {
            "ecological_use": 20,
            "recreation_use": 15
        }

        for field, penalty in supportFields.items():
            value = self.wqFields.get(field)
            if value == "Not Supporting":
                score = score - penalty
            elif value == "Fully Supporting":
                score = score + 10

        # ---fish consumption fields (optional)---
        # only evaluated if user opted in to fish consumption check
        if includeFishSafety:

            # mercury - cause/meeting criteria
            mercuryVal = self.wqFields.get("mercury")
            if mercuryVal == "Cause":
                score = score - 15
            elif mercuryVal == "Meeting Criteria":
                score = score + 5

            # pcbs - strongest consumption hazard
            pcbVal = self.wqFields.get("polychlorinated_biphenyls_pcbs")
            if pcbVal == "Cause":
                score = score - 25
            elif pcbVal == "Meeting Criteria":
                score = score + 5

            # fish consumption use -- fully supporting/not supporting
            fishVal = self.wqFields.get("fishconsumption_use")
            if fishVal == "Not Supporting":
                score = score - 15
            elif fishVal == "Fully Supporting":
                score = score + 10

        # floor at 0 - score cannot go negative
        if score < 0:
            score = 0

        self.score = score
        return self.score

    def setDistance(self, zipCentroid):
        """calculate straight line distance from this fishing point
        to the user zip code centroid.
        distance is in feet (nc state plane)."""
        self.distance = self.geometry.distanceTo(zipCentroid)
        return self.distance

    def toDict(self):
        """return dictionary for csv export and html report."""
        distMiles = round(self.distance / 5280, 2)
        return {
            "rank"           : self.rank,
            "name"           : self.name,
            "score"          : self.score,
            "distance_miles" : distMiles,
            "distance_feet"  : round(self.distance, 2)
        }

# utility functions

def ensureGdb(fc, scratchGdb):
    """checks if the input feature class is a shapefile.
    if it is, copies it to the scratch gdb and returns the gdb path.
    if it is already a gdb feature class, returns the original path.

    this ensures all geoprocessing uses gdb feature classes
    and avoids field name truncation while using spatial join."""
    desc = arcpy.Describe(fc)
    if desc.dataType == "ShapeFile":
        printArc("input is a shapefile copying to scratch gdb")
        fcName  = desc.baseName
        outPath = scratchGdb + "/" + fcName + "_gdb"
        arcpy.management.CopyFeatures(fc, outPath)
        printArc("copied to : {0}".format(outPath))
        return outPath
    else:
        printArc("input is already a gdb feature class -no copy needed.")
        return fc

def getParam(index, default):
    """get parameter by index using sys.argv.
    if argument is not provided, falls back to default value."""
    try:
        value = sys.argv[index + 1]
        if value == "" or value is None:
            printArc("parameter {0} not set, using default: {1}".format(index, default))
            return default
        return value
    except IndexError:
        printArc("parameter {0} not set, using default: {1}".format(index, default))
        return default

def getTopTenExtent(topTenFc, bufferFt=5000):
    """loop through the top ten feature class and
    return the combined extent of all 10 sites
    with a buffer applied to each side."""

    with arcpy.da.SearchCursor(topTenFc, ["SHAPE@"]) as sc:
        extents = [row[0].extent for row in sc]

    xMin = min(ext.XMin for ext in extents) - bufferFt
    yMin = min(ext.YMin for ext in extents) - bufferFt
    xMax = max(ext.XMax for ext in extents) + bufferFt
    yMax = max(ext.YMax for ext in extents) + bufferFt

    return arcpy.Extent(xMin, yMin, xMax, yMax)

def getZipCentroid(zipFc, userZip, zipField, targetSr, scratchGdb):
    """find the zip code polygon matching userZip, reproject to targetSr,
    and return its centroid as an arcpy point geometry."""
    printArc("selecting zip polygon for: {0}".format(userZip))

    # reproject zip code to targetSr
    projectedZip = scratchGdb + "/" + "zip_projected"
    arcpy.management.Project(
        in_dataset      = zipFc,
        out_dataset     = projectedZip,
        out_coor_system = targetSr
    )
    printArc("  zip polygon reprojected to: {0}".format(targetSr.name))

    # extract centroid using where clause in search cursor
    whereClause = "{0} = '{1}'".format(zipField, userZip)
    with arcpy.da.SearchCursor(projectedZip, ["SHAPE@"], whereClause) as sc:
        row = next(sc, None)
        if row is None:
            printArc("error: zip code {0} not found in {1}".format(userZip, zipField))
            return None
        zipPolygon = row[0]

    centroid = zipPolygon.centroid
    centroidPoint = arcpy.PointGeometry(centroid, targetSr)

    printArc("  centroid x : {0}".format(round(centroid.X, 2)))
    printArc("  centroid y : {0}".format(round(centroid.Y, 2)))

    return centroidPoint

def makeADir(thePath):
    """create a directory if file path does not already exist."""
    if not os.path.exists(thePath):
        os.makedirs(thePath)
        printArc("created directory: {0}".format(thePath))

def printArc(message):
    """print message to both pycharm console and arcgis pro script tool window."""
    print(message)
    arcpy.AddMessage(message)

def printArgs():
    """print all user-supplied arguments for debugging."""
    printArc("number of arguments: {0}".format(len(sys.argv)))
    for index, arg in enumerate(sys.argv):
        printArc("  argument {0}: {1}".format(index, arg))

def reprojectLayer(inputFc, outputFc, targetSr):
    """reproject a feature class to the target spatial reference.
    returns path to the reprojected output."""
    arcpy.management.Project(
        in_dataset=inputFc,
        out_dataset=outputFc,
        out_coor_system=targetSr
    )
    printArc("reprojected : {0}".format(outputFc))
    return outputFc

def resolveSpatialRef(srString):
    """convert spatial reference string to arcpy SpatialReference object.
    falls back to wkid 2264 (nad83 nc state plane feet) if parsing fails."""
    try:
        # try as wkid integer first
        sr = arcpy.SpatialReference(int(srString))
        printArc("  spatial reference : {0} (wkid {1})".format(
            sr.name, sr.factoryCode))
        return sr
    except:
        try:
            # try as full projected coordinate system string
            sr = arcpy.SpatialReference()
            sr.loadFromString(srString)
            printArc("  spatial reference : {0}".format(sr.name))
            return sr
        except:
            printArc("  warning: could not parse spatial reference"
                     " - falling back to wkid 2264")
            return arcpy.SpatialReference(2264)

def spatialLinkAttains(fishingFc, attainsLines, targetSr, scratchGdb, scoringFields):
    """link water quality attributes from nearest attains line to each fishing point.
    returns path to output feature class with wq fields joined."""

    printArc("spatial linking")

    # reproject attains lines to match fishing sites coordinate system
    linesProj = scratchGdb + "/" + "attains_lines_proj"
    reprojectLayer(attainsLines, linesProj, targetSr)

    # closest spatial join assigns nearest attains line to each fishing point
    joinOutput = scratchGdb + "/" + "join_closest_lines"
    arcpy.analysis.SpatialJoin(
        target_features   = fishingFc,
        join_features     = linesProj,
        out_feature_class = joinOutput,
        join_operation    = "JOIN_ONE_TO_ONE",
        join_type         = "KEEP_ALL",
        match_option      = "CLOSEST"
    )
    printArc("  closest join complete.")

    # copy fishing sites to output feature class and add scoring fields
    fishingWqFc = scratchGdb + "/" + "fishing_wq_joined"
    arcpy.management.CopyFeatures(fishingFc, fishingWqFc)

    for fieldName in scoringFields:
        arcpy.management.AddField(
            in_table     = fishingWqFc,
            field_name   = fieldName,
            field_type   = "TEXT",
            field_length = 100
        )

    # get the name of the unique id field
    # different for shapefiles (FID) and gdb feature classes
    desc = arcpy.Describe(fishingWqFc)
    oidField = desc.OIDFieldName
    printArc("oid field : {0}".format(oidField))

    # build list of fields to read from join output
    # TARGET_FID identifies which fishing point each row belongs to
    # scoring fields contain the water quality values we need
    readFields = ["TARGET_FID"]
    for fieldName in scoringFields:
        readFields.append(fieldName)

    # read wq values from join output into lookup dictionary
    # { TARGET_FID : { fieldName : value } }
    wqLookup = {}

    with arcpy.da.SearchCursor(joinOutput, readFields) as sc:
        for row in sc:
            fid = row[0]
            wqVals = {}
            for i, fieldName in enumerate(scoringFields, start=1):
                wqVals[fieldName] = row[i]
            wqLookup[fid] = wqVals

    # populate wq fields in output feature class
    # row[0] is oidField so scoring fields start at index 1
    updateFields = [oidField]
    for fieldName in scoringFields:
        updateFields.append(fieldName)

    with arcpy.da.UpdateCursor(fishingWqFc, updateFields) as uc:
        for row in uc:
            fid = row[0]
            for i, fieldName in enumerate(scoringFields, start=1):
                value = wqLookup[fid][fieldName]
                if value is not None:
                    row[i] = str(value)
                else:
                    row[i] = None
            uc.updateRow(row)

    totalPoints = int(arcpy.management.GetCount(fishingWqFc).getOutput(0))
    printArc("total points linked : {0}".format(totalPoints))
    printArc("output feature class : {0}".format(fishingWqFc))

    return fishingWqFc

def validateInputs(layerDict):
    """check that all input paths exist.
    returns True if all valid, False if any are missing."""
    printArc("input validation")
    allValid = True
    for name, path in layerDict.items():
        if arcpy.Exists(path):
            printArc("ok: {0}".format(name))
        else:
            printArc("missing: {0} -> {1}".format(name, path))
            allValid = False
    return allValid



# path setup
scriptPath  = sys.argv[0]
codePath    = os.path.dirname(scriptPath)
baseDir     = os.path.dirname(codePath)
outputDir   = os.path.join(baseDir,   "output")
imageDir    = os.path.join(outputDir, "images")
scratchGdb    = os.path.join(outputDir, "scratch.gdb")
projectPath = os.path.join(baseDir,  "fishing_suitability.aprx")


# user inputs and defaults
fishingFc = getParam(0, os.path.join(baseDir, "data", "public_fishing.shp"))
zipFc     = getParam(1, os.path.join(baseDir, "data", "zip_poly.shp"))
gdbPath   = getParam(2, os.path.join(baseDir, "data", "water_quality.gdb"))
userZip    = getParam(3, "27607")
srString   = getParam(4, "2264")
fishSafety = getParam(5, "false")

# default is false - user must explicitly opt in to fish consumption check
includeFishSafety = fishSafety.strip().lower() == "true"

# resolve spatial reference
targetSr = resolveSpatialRef(srString)

# attains layer path derived from gdb
# only attains lines used for spatial linking
lines = os.path.join(gdbPath, "attains_au_lines")

# confirmed scoring fields from attains schema
coreFields = [
    "isimpaired",
    "on303dlist",
    "ecological_use",
    "oxygen_depletion",
    "pathogens",
    "recreation_use",
    "nutrients",
    "turbidity"
]

fishConsumptionFields = [
    "mercury",
    "polychlorinated_biphenyls_pcbs",
    "fishconsumption_use"
]

# full list of fields to evaluate based on user choice
scoringFields = []
for field in coreFields:
    scoringFields.append(field)

if includeFishSafety:
    for field in fishConsumptionFields:
        scoringFields.append(field)
    printArc("fish consumption fields added to scoring.")
else:
    printArc("fish consumption fields excluded from scoring.")

# environment settings
arcpy.env.overwriteOutput = True
arcpy.env.workspace       = outputDir

# create output directories and scratch gdb
makeADir(outputDir)
makeADir(imageDir)

if not arcpy.Exists(scratchGdb):
    arcpy.management.CreateFileGDB(outputDir, "scratch.gdb")
    printArc("scratch gdb created.")
else:
    printArc("scratch gdb ready.")

# report and validate
printArgs()

inputLayers = {
    "fishing sites"      : fishingFc,
    "zip codes"          : zipFc,
    "water quality gdb"  : gdbPath,
    "attains lines"      : lines,
}

if not validateInputs(inputLayers):
    printArc("\nfix missing inputs above before continuing. exiting.")
    sys.exit(1)

printArc("\n____configuration_____")
printArc("zip code          : {0}".format(userZip))
printArc("fish safety       : {0}".format(includeFishSafety))
printArc("spatial reference : {0}".format(targetSr.name))
printArc("base directory    : {0}".format(baseDir))
printArc("output directory  : {0}".format(outputDir))

# convert shapefile inputs to gdb feature classes
printArc("checking input formats")
fishingFc = ensureGdb(fishingFc, scratchGdb)
zipFc     = ensureGdb(zipFc,     scratchGdb)
printArc("input format check complete.")


# zip field confirmed from getFieldNames defined function
zipField = "ZCTA5CE20"

zipCentroid = getZipCentroid(
    zipFc      = zipFc,
    userZip    = userZip,
    zipField   = zipField,
    targetSr   = targetSr,
    scratchGdb = scratchGdb
)

if zipCentroid is None:
    printArc("could not find zip centroid. exiting.")
    sys.exit(1)
printArc("zip centroid ready for distance calculations.")

# export zip centroid to feature class for mapping
zipCentroidFc = os.path.join(scratchGdb, "zip_centroid")
if arcpy.Exists(zipCentroidFc):
    arcpy.management.Delete(zipCentroidFc)

arcpy.management.CreateFeatureclass(
    out_path          = scratchGdb,
    out_name          = "zip_centroid",
    geometry_type     = "POINT",
    spatial_reference = targetSr
)
arcpy.management.AddField(zipCentroidFc, "zip_code", "TEXT", field_length=10)

with arcpy.da.InsertCursor(zipCentroidFc, ["SHAPE@", "zip_code"]) as ic:
    ic.insertRow([zipCentroid, userZip])
del ic

printArc("zip centroid feature class ready for mapping.")

# link water quality attributes from attains lines
# to each fishing access point using closest spatial join
fishingWqFc = spatialLinkAttains(
    fishingFc     = fishingFc,
    attainsLines  = lines,
    targetSr      = targetSr,
    scratchGdb    = scratchGdb,
    scoringFields = scoringFields
)

printArc("wq joined layer : {0}".format(fishingWqFc))

# create FishingLocation objects, compute scores and distances

sites = []
# build list of fields to read from fishing_wq_joined
# shape@ gives geometry for distance calculation
readFields = ["OID@", "SHAPE@", "PFA_Name"]
for fieldName in scoringFields:
    readFields.append(fieldName)

# read each fishing point and create a FishingLocation object
with arcpy.da.SearchCursor(fishingWqFc, readFields) as sc:
    for row in sc:
        fid  = row[0]
        geom = row[1]
        name = row[2]
        if not name:
            name = "unknown site"

        wqFields = {}
        for i, fieldName in enumerate(scoringFields, start=3):
            wqFields[fieldName] = row[i]

        # create FishingLocation object
        site = FishingLocation(name, fid, geom, wqFields)

        # compute suitability score
        site.computeScore(includeFishSafety)

        # calculate distance from zip centroid
        site.setDistance(zipCentroid)

        sites.append(site)

printArc("{0} fishing locations scored.".format(len(sites)))

printArc("sample scores:")
for s in sites[:5]:
    printArc("{0} score={1}  dist={2:.0f} ft".format(
        s.name, s.score, s.distance))

printArc("\n------------ranking----------")
# rank fishing locations by distance then score
# sort the sites list, using each site's distance value for comparison

sites.sort(key=lambda s: s.distance)
topTen = sites[:10]

# rank those 10 by water quality score
topTen.sort(key=lambda s: s.score, reverse=True)

# assign ranks 1-10 to top 10 sites
for i, site in enumerate(topTen, start=1):
    site.rank = i

# print results
printArc("top 10 fishing locations near zip {0}:".format(userZip))

for site in topTen:
    distMiles = round(site.distance / 5280, 2)
    printArc("\n   rank {0} : {1}".format(site.rank, site.name))
    printArc("   score     : {0}".format(site.score))
    printArc("   distance  : {0} miles".format(distMiles))

# export top 10 to feature class using select by oid
oids        = [str(site.fid) for site in topTen]
whereClause = "OBJECTID IN ({0})".format(",".join(oids))

topTenFc      = os.path.join(scratchGdb, "topTen_fishing_sites")
arcpy.analysis.Select(
    in_features       = fishingWqFc,
    out_feature_class = topTenFc,
    where_clause      = whereClause
)
# add rank and score fields to top10 feature class
arcpy.management.AddField(topTenFc, "rank",  "SHORT")
arcpy.management.AddField(topTenFc, "score", "SHORT")

rankScoreDict = {}
for site in topTen:
    rankScoreDict[site.name] = (site.rank, site.score)

# populate rank and score by matching site name
with arcpy.da.UpdateCursor(topTenFc, ["PFA_Name", "rank", "score"]) as uc:
    for row in uc:
        name = row[0]
        if name in rankScoreDict:
            row[1] = rankScoreDict[name][0]
            row[2] = rankScoreDict[name][1]
            uc.updateRow(row)
printArc("rank and score fields populated for {0}".format(topTenFc))

# getting extent of the top 10 points for layout
xtent = getTopTenExtent(topTenFc)

printArc("top 10 sites exported as {0} and ready for mapping".format(topTenFc))


printArc("\n------------mapping----------")

# open arcgis pro project
try:
    # When working inside ArcGIS Pro,
    # use the project name "CURRENT"
    aprx = arcpy.mp.ArcGISProject("CURRENT")

except OSError:
    # When working outside ArcGIS Pro,
    # use the project full path file name.
    aprx = arcpy.mp.ArcGISProject(projectPath)

myMap = aprx.listMaps()[0]
printArc("  project opened : {0}".format(projectPath))
printArc("  map            : {0}".format(myMap.name))

# remove existing layers if present from previous runs
for lyr in myMap.listLayers():
    if lyr.name in (os.path.basename(topTenFc), os.path.basename(zipCentroidFc)):
        printArc("removing existing layer : {0}".format(lyr.name))
        myMap.removeLayer(lyr)

# add top10 feature layer and apply graduated symbol renderer by score
topTenLayer = myMap.addDataFromPath(topTenFc)
sym = topTenLayer.symbology
sym.updateRenderer("GraduatedSymbolsRenderer")
sym.renderer.classificationField = "score"
sym.renderer.breakCount          = 5


# set color to blue and sizes for all class breaks
sizes = [8, 12, 16, 20, 27]
for i, brk in enumerate(sym.renderer.classBreaks):
    brk.symbol.color = {"RGB" : [0, 92, 230, 100]}
    brk.symbol.size  = sizes[i]
topTenLayer.symbology = sym
printArc("top 10 feature layer added with graduated colors symbology.")

# add zip centroid layer and apply symbology
zipLayer = myMap.addDataFromPath(zipCentroidFc)
sym = zipLayer.symbology
sym.renderer.symbol.applySymbolFromGallery("Push Pin 1")
sym.renderer.symbol.color = {"RGB" : [201, 49, 0, 100]}
zipLayer.symbology = sym
printArc("zip centroid layer added to map.")

# save a copy and release project lock
aprx.saveACopy(os.path.join(outputDir, "fishing_suitability_mapped.aprx"))
del aprx
printArc("project saved.")


printArc("\n------------html report----------")

# export map screenshot from layout
try:
    # When working inside ArcGIS Pro,
    # use the project name "CURRENT"
    aprx = arcpy.mp.ArcGISProject("CURRENT")

except OSError:
    # When working outside ArcGIS Pro,
    # use the project full path file name.
    aprx = arcpy.mp.ArcGISProject(projectPath)

myMap  = aprx.listMaps()[0]
fishingLayout   = aprx.listLayouts()[0]
imageName  = os.path.join(imageDir, "fishing_map_{0}.png".format(userZip))
mf = fishingLayout.listElements('MAPFRAME_ELEMENT')[0]
mf.camera.setExtent(xtent)
fishingLayout.exportToPNG(imageName, resolution=300)
printArc("map image exported : {0}".format(imageName))
del aprx

relImagePath = os.path.relpath(imageName, outputDir)

# build table rows by looping over topTen and calling toDict()
tableRows = ""
for site in topTen:
    d = site.toDict()
    tableRows += "<tr><td>{0}</td><td>{1}</td>".format(
        d["rank"], d["name"])
    tableRows += "<td>{0}</td><td>{1}</td></tr>".format(
        d["score"], d["distance_miles"])

# optional fish safety note for html
fishConsumptionNote = ""
if includeFishSafety :
    fishConsumptionNote =("<p style='font-family:verdana; color:grey;'>"
    "Fish consumption safety included in scoring.</p>")

beginning = """<!DOCTYPE html>
<html>
<body bgcolor='AliceBlue'>"""

middle = """
<h1 style="font-family:verdana; color:grey;">
    NC Fishing Suitability Report
</h1>

<p style="font-family:verdana; color:grey;">
    Top 10 public fishing locations near zip code {0}.
    Ranked by water quality suitability score.
</p>

<figure>
    <img src="{1}" alt="Map of top 10 fishing sites
         near zip code {0}." width="600">
    <figcaption style="width:600px;
                       font-family:verdana;
                       color:gray;">
        Top 10 fishing access points near zip code {0},
        displayed with graduated symbols by suitability
        score. Larger symbols indicate higher water
        quality scores.
    </figcaption>
</figure>

<h2 style="font-family:verdana; color:grey;">
    Results
</h2>
{3}
<table border="3" style="font-family:verdana; color:grey;">
    <tr>
        <th>Rank</th>
        <th>Site Name</th>
        <th>Score</th>
        <th>Distance (miles)</th>
    </tr>
{2}
</table>""".format(userZip, relImagePath, tableRows, fishConsumptionNote)

end = """
</body>
</html>"""


htmlFile = os.path.join(outputDir, "fishing_report.html")
with open(htmlFile, "w") as outf:
    outf.write(beginning)
    outf.write(middle)
    outf.write(end)

printArc("html report created : {0}".format(htmlFile))

# auto-open in browser
os.startfile(htmlFile)
printArc("report opened in browser.")
