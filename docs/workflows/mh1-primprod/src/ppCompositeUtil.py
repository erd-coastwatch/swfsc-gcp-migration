def meanVar(mean, num, pprod):
    """Update a legacy running mean and observation-count array."""
    import numpy as np
    import numpy.ma as ma

    numShape = num.shape
    temp = np.subtract(pprod, mean, dtype=np.single)

    numAdd = np.ones(numShape, dtype=np.int32)
    numAdd[pprod.mask] = 0

    num = np.add(num, numAdd, dtype=np.int32)
    tempNum = ma.array(num, mask=(num == 0), dtype=np.int32)

    temp = temp / tempNum.astype("float")
    mean = np.add(mean, temp.filled(0.0), dtype=np.single)

    return mean, num


def isleap(year):
    """Return True when year is a leap year."""
    from datetime import date

    try:
        date(year, 2, 29)
        return True
    except ValueError:
        return False


def MWPProdFilelist(year, enddoy, interval, dataDir):
    """Return MODIS-West primary productivity files for a composite window."""
    import os
    from datetime import datetime, timedelta

    day_range = range(0, interval)
    end_date = datetime(year, 1, 1) + timedelta(enddoy - 1)

    os.chdir(dataDir)

    fileList = []

    for day in day_range:
        myDate = end_date + timedelta(days=-day)
        doy = myDate.strftime("%j")
        yr = myDate.strftime("%Y")

        myString = "MWPrimProd" + yr + doy + "_" + yr + doy + ".nc"

        if os.path.isfile(myString):
            fileList.append(myString)

    fileList.sort()
    return fileList


def MHPProdFilelist(year, enddoy, interval, dataDir):
    """Return MODIS-MH1 primary productivity files for a composite window."""
    import os
    from datetime import datetime, timedelta

    day_range = range(0, interval)
    end_date = datetime(year, 1, 1) + timedelta(enddoy - 1)

    os.chdir(dataDir)

    fileList = []

    for day in day_range:
        myDate = end_date + timedelta(days=-day)
        doy = myDate.strftime("%j")
        yr = myDate.strftime("%Y")

        myString = "A" + yr + doy + ".L3m_DAY_primprod.nc"

        if os.path.isfile(myString):
            fileList.append(myString)

    fileList.sort()
    return fileList


def MWcomposite(year, enddoy, interval, dataDir, outDir):
    """Create a legacy MODIS-West primary productivity composite."""
    import os
    import time as tp
    import numpy as np
    import numpy.ma as ma
    from netCDF4 import Dataset, date2num
    from datetime import datetime, timedelta

    os.chdir(dataDir)

    fileList = MWPProdFilelist(year, enddoy, interval, dataDir)

    mean = np.zeros((2321, 4001), np.single)
    num = np.zeros((2321, 4001), dtype=np.int32)

    history = " " + str(interval) + "-day composite mean of files"

    if len(fileList) == 0:
        return

    for fName in fileList:
        print(fName)
        history = history + " " + fName

        PPROD = Dataset(fName, "r")
        pprod = PPROD.variables["MWPProd"][:, :]
        pprod = np.squeeze(pprod)
        PPROD.close()

        mean, num = meanVar(mean, num, pprod)

    mean = ma.array(mean, mask=(num == 0), fill_value=-99999.0)

    compmid = interval / 2.0
    endDate = datetime(year, 1, 1) + timedelta(enddoy - 1)
    startDate = endDate + timedelta(days=-(interval - 1))
    myDate = startDate + timedelta(days=compmid)

    yearstart = str(startDate.year)
    doystart = startDate.strftime("%j").zfill(3)
    yearend = str(endDate.year)
    doyend = str(enddoy).rjust(3, "0")

    PPROD = Dataset(fileList[0], "r")
    latdata = PPROD.variables["latitude"][:]
    londata = PPROD.variables["longitude"][:]
    PPROD.close()

    myTime = date2num(myDate, units="seconds since 1970-01-01")

    ncfile = Dataset("temp.nc", "w")

    lonsdim = londata.shape[0]
    latsdim = latdata.shape[0]

    ncfile.createDimension("nav", 2)
    ncfile.createDimension("altitude", 1)
    ncfile.createDimension("latitude", latsdim)
    ncfile.createDimension("longitude", lonsdim)
    ncfile.createDimension("time", 1)

    latitude = ncfile.createVariable("latitude", "f8", ("latitude",))
    longitude = ncfile.createVariable("longitude", "f8", ("longitude",))
    altitude = ncfile.createVariable("altitude", "f8", ("altitude",))
    time = ncfile.createVariable("time", "f8", ("time",))
    time_bnds = ncfile.createVariable("time_bnds", "f8", ("time", "nav"))
    nob = ncfile.createVariable(
        "nobs", "i4", ("time", "altitude", "latitude", "longitude")
    )
    primprod = ncfile.createVariable(
        "MWPProd",
        "f4",
        ("time", "altitude", "latitude", "longitude"),
        fill_value=-99999.0,
    )

    time.actual_range = str(myTime) + ", " + str(myTime)
    time.long_name = "Centered Time"
    time.units = "seconds since 1970-01-01T00:00:00Z"
    time.standard_name = "time"
    time.axis = "T"
    time._CoordinateAxisType = "Time"

    time_bnds.units = "seconds since 1970-01-01T00:00:00Z"
    time_bnds.standard_name = "time"

    altitude.actual_range = "0.0, 0.0"
    altitude.long_name = "Altitude"
    altitude.positive = "up"
    altitude.standard_name = "altitude"
    altitude.units = "m"
    altitude.axis = "Z"
    altitude._CoordinateAxisType = "Height"
    altitude._CoordinateZisPositive = "up"

    latitude._CoordinateAxisType = "Lat"
    latitude.actual_range = "22.0, 51.0"
    latitude.coordsys = "geographic"
    latitude.long_name = "Latitude"
    latitude.point_spacing = "even"
    latitude.standard_name = "latitude"
    latitude.units = "degrees_north"
    latitude.axis = "Y"

    longitude._CoordinateAxisType = "Lon"
    longitude.actual_range = "205.0, 255.0"
    longitude.coordsys = "geographic"
    longitude.long_name = "Longitude"
    longitude.point_spacing = "even"
    longitude.standard_name = "longitude"
    longitude.units = "degrees_east"
    longitude.axis = "X"

    primprod.coordsys = "geographic"
    primprod.long_name = (
        "Primary Productivity, Aqua MODIS, NPP, West Coast, EXPERIMENTAL"
    )
    primprod.missing_value = -99999.0
    primprod.standard_name = "net_primary_productivity_of_carbon"
    primprod.units = "mg C m-2 day-1"

    nob.long_name = "Number of observations in composite"
    nob.missing_value = -99999

    ncfile.Conventions = "Conventions: CF-1.6, COARDS, ACDD-1.3"
    ncfile.title = (
        str(interval)
        + "-day composite mean of Primary Productivity, Aqua MODIS, NPP, West Coast, EXPERIMENTAL"
    )
    ncfile.references = "Behrenfield and Falkowski, L&O 1997"
    ncfile.summary = (
        "calculates the composite of vertically integrated primary productivity "
        "one day files that use the Behrenfield - Falkowski method and "
        "satellite-based measurements of Chlorophyll a, incident visible surface "
        "irradiance, and sea surface temperature. see Behrenfield and Falkowski, "
        "L&O 1997."
    )
    ncfile.institution = "NOAA NMFS SWFSC ERD"
    ncfile.contact = "erd.data@noaa.gov"
    ncfile.creator_name = "erd.data"
    ncfile.creator_email = "erd.data@noaa.gov"
    ncfile.creation_date = tp.strftime("%c")
    ncfile.spatial_resolution = "0.0125 degree"
    ncfile.source_data = history
    ncfile.Southernmost_Northing = 22.0
    ncfile.Northernmost_Northing = 51.0
    ncfile.Westernmost_Easting = 205.0
    ncfile.Easternmost_Easting = 255.0
    ncfile.rights = (
        "The data may be used and redistributed for free but is not intended "
        "for legal use, since it may contain inaccuracies. Neither the data "
        "Contributor, CoastWatch, NOAA, nor the United States Government, nor "
        "any of their employees or contractors, makes any warranty, express or "
        "implied, including warranties of merchantability and fitness for a "
        "particular purpose, or assumes any legal liability for the accuracy, "
        "completeness, or usefulness, of this information."
    )
    ncfile.history = ""

    latitude[:] = latdata
    longitude[:] = londata
    primprod[0, 0, :, :] = mean[:, :]
    nob[0, 0, :, :] = num[:, :]
    time[0] = myTime
    altitude[0] = 0.0

    myTime = date2num(startDate, units="seconds since 1970-01-01")
    time_bnds[0, 0] = myTime

    myTime = startDate + timedelta(days=interval)
    myTime = date2num(myTime, units="seconds since 1970-01-01")
    time_bnds[0, 1] = myTime

    ncfile.close()

    ncFileName = (
        "MWPProd"
        + yearstart
        + doystart
        + "_"
        + yearend
        + doyend
        + "_"
        + str(interval)
        + "day_primprod.nc"
    )

    os.system("cp " + dataDir + "/temp.nc " + outDir + "/" + ncFileName)
    os.system("scp " + outDir + "/" + ncFileName + " cwatch@192.168.31.27:" + outDir)
    os.system("rm -f temp.nc")


def MHcomposite(year, enddoy, interval, dataDir, outDir):
    """Create a legacy MODIS-MH1 primary productivity composite."""
    import os
    import time as tp
    import numpy as np
    import numpy.ma as ma
    from netCDF4 import Dataset, date2num
    from datetime import datetime, timedelta

    os.chdir(dataDir)

    fileList = MHPProdFilelist(year, enddoy, interval, dataDir)

    mean = np.zeros((4320, 8640), np.single)
    num = np.zeros((4320, 8640), dtype=np.int32)

    history = " " + str(interval) + "-day composite mean of files"

    if len(fileList) == 0:
        return

    for fName in fileList:
        print(fName)
        history = history + " " + fName

        PPROD = Dataset(fName, "r")
        pprod = PPROD.variables["MHPProd"][:, :]
        pprod = np.squeeze(pprod)
        PPROD.close()

        mean, num = meanVar(mean, num, pprod)

    mean = ma.array(mean, mask=(num == 0), fill_value=-99999.0)

    compmid = interval / 2.0
    endDate = datetime(year, 1, 1) + timedelta(enddoy - 1)
    startDate = endDate + timedelta(days=-(interval - 1))
    myDate = startDate + timedelta(days=compmid)

    yearstart = str(startDate.year)
    doystart = startDate.strftime("%j").zfill(3)
    yearend = str(endDate.year)
    doyend = str(enddoy).rjust(3, "0")

    PPROD = Dataset(fileList[0], "r")
    latdata = PPROD.variables["latitude"][:]
    londata = PPROD.variables["longitude"][:]
    PPROD.close()

    myTime = date2num(myDate, units="seconds since 1970-01-01")

    ncfile = Dataset("temp.nc", "w")

    lonsdim = londata.shape[0]
    latsdim = latdata.shape[0]

    ncfile.createDimension("nav", 2)
    ncfile.createDimension("altitude", 1)
    ncfile.createDimension("longitude", lonsdim)
    ncfile.createDimension("latitude", latsdim)
    ncfile.createDimension("time", 1)

    latitude = ncfile.createVariable("latitude", "f8", ("latitude",))
    longitude = ncfile.createVariable("longitude", "f8", ("longitude",))
    altitude = ncfile.createVariable("altitude", "f8", ("altitude",))
    time = ncfile.createVariable("time", "f8", ("time",))
    time_bnds = ncfile.createVariable("time_bnds", "f8", ("time", "nav"))
    nob = ncfile.createVariable(
        "nobs", "i4", ("time", "altitude", "latitude", "longitude")
    )
    primprod = ncfile.createVariable(
        "MHPProd",
        "f4",
        ("time", "altitude", "latitude", "longitude"),
        fill_value=-99999.0,
    )

    time.actual_range = str(myTime) + ", " + str(myTime)
    time.long_name = "Centered Time"
    time.units = "seconds since 1970-01-01T00:00:00Z"
    time.standard_name = "time"
    time.axis = "T"
    time._CoordinateAxisType = "Time"

    time_bnds.units = "seconds since 1970-01-01T00:00:00Z"
    time_bnds.standard_name = "time"

    altitude.actual_range = "0.0, 0.0"
    altitude.long_name = "Altitude"
    altitude.positive = "up"
    altitude.standard_name = "altitude"
    altitude.units = "m"
    altitude.axis = "Z"
    altitude._CoordinateAxisType = "Height"
    altitude._CoordinateZisPositive = "up"

    latitude._CoordinateAxisType = "Lat"
    latitude.actual_range = "-89.97918, 89.97918"
    latitude.coordsys = "geographic"
    latitude.long_name = "Latitude"
    latitude.point_spacing = "even"
    latitude.standard_name = "latitude"
    latitude.units = "degrees"
    latitude.axis = "Y"

    longitude._CoordinateAxisType = "Lon"
    longitude.actual_range = "-179.9792, 179.9792"
    longitude.coordsys = "geographic"
    longitude.long_name = "Longitude"
    longitude.point_spacing = "even"
    longitude.standard_name = "longitude"
    longitude.units = "degrees"
    longitude.axis = "X"

    primprod.coordsys = "geographic"
    primprod.long_name = (
        "Primary Productivity, Aqua MODIS, NPP, West Coast, EXPERIMENTAL"
    )
    primprod.missing_value = -99999.0
    primprod.standard_name = "net_primary_productivity_of_carbon"
    primprod.units = "mg C m-2 day-1"

    nob.long_name = "Number of observations in composite"
    nob.missing_value = -99999

    ncfile.Conventions = "Conventions: CF-1.6, COARDS, ACDD-1.3"
    ncfile.title = (
        str(interval)
        + "-day composite mean of Primary Productivity, Aqua MODIS, NPP, West Coast, EXPERIMENTAL"
    )
    ncfile.references = "Behrenfield and Falkowski, L&O 1997"
    ncfile.summary = (
        "calculates the composite of vertically integrated primary productivity "
        "one day files that use the Behrenfield - Falkowski method and "
        "satellite-based measurements of Chlorophyll a, incident visible surface "
        "irradiance, and sea surface temperature. see Behrenfield and Falkowski, "
        "L&O 1997."
    )
    ncfile.institution = "NOAA NMFS SWFSC ERD"
    ncfile.contact = "erd.data@noaa.gov"
    ncfile.creator_name = "erd.data"
    ncfile.creator_email = "erd.data@noaa.gov"
    ncfile.creation_date = tp.strftime("%c")
    ncfile.spatial_resolution = "0.0125 degree"
    ncfile.source_data = history
    ncfile.Southernmost_Northing = -89.97918
    ncfile.Northernmost_Northing = 89.97918
    ncfile.Westernmost_Easting = -179.9792
    ncfile.Easternmost_Easting = 179.9792
    ncfile.rights = (
        "The data may be used and redistributed for free but is not intended "
        "for legal use, since it may contain inaccuracies. Neither the data "
        "Contributor, CoastWatch, NOAA, nor the United States Government, nor "
        "any of their employees or contractors, makes any warranty, express or "
        "implied."
    )
    ncfile.history = ""

    latitude[:] = latdata
    longitude[:] = londata
    time[0] = myTime
    nob[0, 0, :, :] = num[:, :]
    primprod[0, 0, :, :] = mean[:, :]
    altitude[0] = 0.0

    myTime = date2num(startDate, units="seconds since 1970-01-01")
    time_bnds[0, 0] = myTime

    myTime = startDate + timedelta(days=interval)
    myTime = date2num(myTime, units="seconds since 1970-01-01")
    time_bnds[0, 1] = myTime

    ncfile.close()

    ncFileName = (
        "A"
        + yearstart
        + doystart
        + "_"
        + yearend
        + doyend
        + ".L3m_"
        + str(interval)
        + "day_primprod.nc"
    )

    os.system("cp " + dataDir + "/temp.nc " + outDir + "/" + ncFileName)
    os.system("scp " + outDir + "/" + ncFileName + " cwatch@192.168.31.27:" + outDir)
    os.system("scp " + outDir + "/" + ncFileName + " cwatch@192.168.31.15:" + outDir)
    os.system("rm -f temp.nc")
