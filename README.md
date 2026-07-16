# Freshwater Fishing Suitability

ArcGIS Pro geoprocessing tool that ranks freshwater fishing locations by water quality, proximity, and fish consumption safety,

## Overview

Public fishing access locations are easy to find, but knowing whether a fishing spot is actually suitable or safe to consume fish from is much more challenging. Doing so requires combining water quality assessments, proximity analysis, and, when desired, fish consumption advisories into a single decision-making workflow.

This ArcGIS Pro geoprocessing tool automates that process. Given a user-specified ZIP code, it identifies nearby public fishing access locations and ranks them using a rule-based suitability scoring system based on water quality and proximity. Users can optionally incorporate fish consumption safety criteria, such as mercury and PCB advisories, to identify locations that are not only accessible but also safer for recreational fishing.

This repository demonstrates the workflow using publicly available datasets from North Carolina. However, the tool is designed to be reusable and can be adapted for other states or regions by substituting equivalent public fishing access, water quality, and ZIP code datasets.

## Key Features

- Interactive ArcGIS Pro geoprocessing tool with a user-friendly interface
- Accepts a user-specified ZIP code to identify nearby public fishing locations
- Integrates public fishing access locations with EPA water quality assessments
- Uses a rule-based suitability scoring system to rank fishing locations
- Optional fish consumption safety analysis incorporating mercury and PCB advisories
- Filters to the 10 nearest fishing locations by distance, then ranks them by suitability score
- Generates a ranked feature class for visualization in ArcGIS Pro
- Produces an HTML report summarizing analysis results
- Designed to be reusable with equivalent datasets from other states or regions

## Tool Interface

The Freshwater Fishing Suitability tool is implemented as an ArcGIS Pro geoprocessing script tool. The interface provides a concise set of configurable parameters while supplying sensible defaults for the North Carolina demonstration workflow.

- **Input Datasets:** Default paths point to the North Carolina demonstration datasets and can be replaced with equivalent public fishing access, water quality, and ZIP code datasets from other states or regions.
- **ZIP Code:** Defaults to **27607 (Raleigh, NC)** for demonstration purposes and accepts any valid ZIP code within the study area.
- **Output Coordinate System:** Defaults to **NAD 1983 StatePlane North Carolina FIPS 3200 (Feet)** and can be changed to match the coordinate system of other GIS projects.
- **Fish Consumption Safety:** Disabled by default and can be enabled to incorporate mercury and PCB advisories into the suitability scoring process.

![ArcGIS Pro Tool Interface](images/tool-interface.png)

*Figure 1. ArcGIS Pro geoprocessing interface for the Freshwater Fishing Suitability geoprocessing tool.*

## Workflow

The Freshwater Fishing Suitability tool follows the workflow below to identify and rank suitable public fishing locations.

```text
User Input
      │
      ▼
Set up output directories and scratch geodatabase
      │
      ▼
Validate all required input datasets
      │
      ▼
Convert shapefile inputs to geodatabase feature classes to prevent field name truncation
      │
      ▼
Locate the user by calculating the centroid of the selected ZIP code
      │
      ▼
Reproject water quality data to the selected output coordinate system
      │
      ▼
Spatially join each fishing access point to the nearest EPA ATTAINS water quality line feature
      │
      ▼
Calculate suitability scores using water quality attributes
(optionally incorporating fish consumption safety criteria)
      │
      ▼
Calculate distances from the ZIP code centroid
      │
      ▼
Filter to the 10 nearest fishing locations
      │
      ▼
Rank locations by suitability score
      │
      ▼
Generate output feature classes, map visualization, and HTML report
```
## Project Outputs

Running the Freshwater Fishing Suitability tool generates the following outputs:

- **Top 10 Fishing Locations** – A feature class containing the 10 highest-ranked freshwater fishing locations, including suitability scores, associated water quality attributes, and distance from the selected ZIP code.
- **HTML Report** – An automatically generated report summarizing the analysis with a map of the ranked fishing locations and a results table containing the site name, suitability score, and distance from the selected ZIP code.

### HTML Report

<p align="center">
  <img src="images/html-report.png" alt="HTML Report" width="700">
</p>

*Figure 2. Automatically generated HTML report displaying the ranked fishing locations, suitability scores, distances, and map visualization.*
