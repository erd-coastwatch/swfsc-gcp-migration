def BFprimprod(chl,par,sst,daylen):
   """Calculate vertically integrated primary productivity from CHL, PAR, SST, and daylength."""
   import numpy as np
   import numpy.ma as ma
# start building parameters.
#  first get Euphotic zone based on CHL and Morel and Berthon (L&O, 1989)
# np.power raise array chl to .425 in this case

   ctot = ma.array(38* np.power(chl , .425))
   # find eutrophic data
   #creates a mask to index by in order to only changes numbers in chl >=1
   mask = (chl >= 1)
   ctot[mask] = 40.2 * np.power(chl[mask] , .507)
   Zeu = 568.2 * np.power(ctot , -0.746)
   # find murky water
   mask = ctot > 102
   Zeu[mask] = 200 * np.power(ctot[mask] , -.293)

# calculate Pb-opt using SST (Behrenfield and Falkowski (L&O, 1997)
   PBopt = 1.2956 + (2.749e-1 * sst)  + (6.17e-2 * np.multiply(sst,sst) )  \
           - (2.05e-2 * np.power(sst,3)) + (2.462e-3 * np.power(sst ,4)) \
           - (1.348e-4 * np.power(sst,5)) + (3.4132e-6 * np.power(sst ,6)) \
           - (3.27e-8 * np.power(sst,7))

   # correct for very cold water
   mask = ma.logical_and(~PBopt.mask,(sst <  -1))
   PBopt[mask] = 1.13

   # correct for fairly warm water
   mask = ma.logical_and(~PBopt.mask,(sst >  28.5))
   PBopt[mask] = 4.0

# ready for productivity calculation.
#   prod = .66125 * PBopt .* (par./(par+4.1)) .* chl .* Zeu .* daylen
   prod=np.divide(par,(par+4.1))
   prod=np.multiply((.66125 * PBopt), prod)
   prod=np.multiply(prod,chl)
   prod=np.multiply(prod,Zeu)
# daylen[:,np.newaxis] allows the 2321 by 4001 to be multiplied by daylen
   prod=np.multiply(prod,daylen)

   return(prod)


def daylength(lat,doy,method):
   """Calculate decimal-hour daylength from latitude and day-of-year."""
# Function DAYLENGTH calculates the time between sunrise and sunset
# based on latitude and day of year.
#
# INPUTS:
#   latitude -- can be a scalar, vector or matrix in degrees N (-90 to 90)
#   doy -- is day of year (1-366, January 1 = 1)
#   method -- "brock" or "forsythe";
#            1 uses Brock method with Spencer declination
#            2 uses Brock method with Bourges declination
#            anything else (default) is Forsythe et al. method.
#
#   As in: Bourges, B. 1985. Improvement in solar declination computation.
#          Solar Energy 35(4), 367-369
#
#          Brock, T.D. 1981.  Calculating solar radiation for ecological studie
#          Ecol. Modell. 14:81-82
#
#          Forsythe,W.C., Rykiel,E.J.,Stahl,R.S.,Wu, H,Schoolfield, R.M. 1995
#          A model comparison for daylength as a function of latitude and
#          day of year. Ecological Modelling 80: 87-95
#
#          Spencer, J.W. 1971. Fourier series representation of the position
#          of the sun.  Search. 2(5), 172.
#
# OUTPUT:
#   daylength - will be in decimal hours with same dimensions as latitude.
#
   import numpy as np

# set up useful constants
   pi=np.pi
   deg2rad = 2 * pi /360.

# identify method
   if ( method == 1):

   # get day angle
      td = 2*pi*(doy -1)/365

   # get declination angle
      decl = 0.006918 - 0.399912 * np.cos(td) + 0.070257 * np.sin(td) \
      - 0.006758 * np.cos(2*td) + 0.000907 * np.sin(2*td) \
      - 0.002697 * np.cos(3*td) + 0.001480 * np.sin(3*td)

   # calculate daylength
      daylength = (24/pi) * np.arccos(-np.tan(decl) * np.tan(lat*deg2rad))

   elif ( method == 2):

   # get day angle
      td = (2*pi/365.25)*(doy - 79.346)

   # get declination angle
      decl = (pi/180)* (0.3723 + 23.2567 * np.sin(td) - 0.758 * np.cos(td) \
      + 0.1149 * np.sin(2*td) + 0.3656 * np.cos(2*td) \
      - 0.1712 * np.sin(3*td) + 0.0201 * np.cos(3*td))

   # calculate daylength
      daylength = (24/pi) * np.arccos( -np.tan(decl)*np.tan(lat*deg2rad))

   else:

   # get declination
      decl = np.arcsin(.39795*np.cos(.2163108 + 2*np.arctan(.9671396*np.tan(.0086*(doy-186)))))

   # calculate daylength
      denom = np.cos(lat*deg2rad) * np.cos(decl)
      temp = (np.sin(0*pi/180) + np.sin(lat*deg2rad)*np.sin(decl)) / denom
      temp[temp < -1] = -1
      temp[temp > 1] = 1
      daylength = 24 - (24/pi) * np.arccos(temp)
#       daylength = 24 - (24/pi) * acos ( (sin(.833*pi/180) + sin(lat*deg2rad)*sin(decl)) ./ denom);

   return(daylength)


def isleap(year):
    """Return True when year is a leap year."""
    import os, sys
    from datetime import date, datetime, timedelta
    try:
        date(year,2,29)
        return True
    except ValueError: return False

def MWPProductivity(years):
  """Run the legacy MODIS-West daily primary productivity workflow."""

  import numpy as np
  import operator
  from netCDF4 import Dataset, num2date, date2num
  import numpy.ma as ma
  import glob, os, sys
  from datetime import date, datetime, timedelta
# define the data directories
  parDir = "/u00/satellite/MW/par0/1day/"
  sstDir = "/u00/satellite/MW/sstd/1day/"
  chlaDir = "/u00/satellite/MW/chla/1day/"
  ppDir = "/u00/satellite/PP2/1day/"
# date for creation date
  today=date.today()
#Load in daylen.nc
  DAYLEN = Dataset('daylen.nc', 'r', format='NETCDF3_CLASSIC')

#Load variables lat, lon, and daylen from nc file
  lat = DAYLEN.variables['lat'][:]
  lon = DAYLEN.variables['lon'][:]
  daylen1 = DAYLEN.variables['daylen']


#Loop through year and date
  for year1 in years:

      print(year1)
      year=str(year1)
      if(isleap(year1)):
          days=range(1,367)
      else:
          days=range(1,366)
      for doy in days:

          print(doy)
          myDate = datetime(year1, 1, 1) + timedelta(doy-1)
          myTime = date2num(myDate,units='seconds  since 1970-01-01')
          myTime= myTime + 43200
          day=str(doy)
          day=day.rjust(3,'0')
          daylen = daylen1[doy-1,:,:]

          filenameSSTD = 'MW' + year + day + '_' + year + day + '_sstd.nc'
          filenamePAR  ='MW' + year + day + '_' + year + day + '_par0.nc'
          filenameCHLA = 'MW' + year + day + '_' + year + day + '_chla.nc'

# Load NETCDF4 Files
          sstTest = os.path.isfile(sstDir+filenameSSTD)
          chlaTest = os.path.isfile(chlaDir+filenameCHLA)
          parTest = os.path.isfile(parDir+filenamePAR)
          if (sstTest and chlaTest and parTest):
             print('found files')
             SSTD = Dataset(sstDir+filenameSSTD, 'r')
             PAR  = Dataset(parDir+filenamePAR, 'r')
             CHLA = Dataset(chlaDir+filenameCHLA, 'r')


#Pull out the variables from each file needed for production calculation
             sst = SSTD.variables['MWsstd'][:,:,:,:]
             par = PAR.variables['MWpar0'][:,:,:,:]
             chl = CHLA.variables['MWchla'][:,:,:,:]


#Pull out data array from above variables
             sst = np.squeeze(sst)
             par = np.squeeze(par)
             chl = np.squeeze(chl)

# Calculate Productivity
             prod = BFprimprod(chl,par,sst,daylen)
             ma.set_fill_value(prod,-99999)

# Save as netcdf
#create dimensions for prod
             latsdim = lat.shape[0]
             lonsdim = lon.shape[0]


#dataset creation
             ppFile = ppDir + 'MWPrimProd' + year + day + '_' + year + day + '.nc'
             ncfile = Dataset('temp.nc', 'w')

#create dimensions
             latdim = ncfile.createDimension('latitude', latsdim)
             londim = ncfile.createDimension('longitude', lonsdim)
             timedim= ncfile.createDimension('time', 1)
             altitude = ncfile.createDimension('altitude', 1)

#create variables
             latitude = ncfile.createVariable('latitude','f4',('latitude'))
             longitude = ncfile.createVariable('longitude','f4',('longitude'))
             altitude = ncfile.createVariable('altitude','f4',('altitude'))
             time = ncfile.createVariable('time','i4',('time'))
             primprod = ncfile.createVariable('MWPProd','f4',('time','altitude','latitude','longitude'),fill_value=-99999.0)
#attributes
#
#time attributes
             time.actual_range=str(myTime) + ', ' + str(myTime)
             time.long_name = 'Centered Time'
             time.units =  'seconds since 1970-01-01T00:00:00Z'
             time.standard_name = 'time'
             time.axis =  'T'
             time._CoordinateAxisType =  'Time'
#altitude attributes
             altitude.actual_range =  '0.0, 0.0'
             altitude.long_name =  'Altitude'
             altitude.positive =  'up'
             altitude.standard_name =  'altitude'
             altitude.units = 'm'
             altitude.axis =  'Z'
             altitude._CoordinateAxisType = 'Height'
             altitude._CoordinateZisPositive =  'up'
#latitude attributes
             latitude._CoordinateAxisType =  'Lat'
             latitude.actual_range =  '22.0, 51.0'
             latitude.coordsys = 'geographic'
             latitude.long_name = 'Latitude'
             latitude.point_spacing = 'even'
             latitude.standard_name = 'latitude'
             latitude.units = 'degrees_north'
             latitude.axis = 'Y'
#longitude attributes
             longitude._CoordinateAxisType = 'Lon'
             longitude.actual_range =  '205.0, 255.0'
             longitude.coordsys =  'geographic'
             longitude.long_name =  'Longitude'
             longitude.point_spacing =  'even'
             longitude.standard_name =  'longitude'
             longitude.units =  'degrees_east'
             longitude.axis =  'X'
#primprod attributes
             primprod.coordsys =  'geographic'
             primprod.long_name =  'Primary Productivity, Aqua MODIS, NPP, West Coast, EXPERIMENTAL'
             primprod.missing_value =  -99999.0
             primprod.standard_name =  'net_primary_productivity_of_carbon'
             primprod.units = 'mg C m-2 day-1'
#  global attributes
             ncfile.Conventions = 'CF-1.6, COARDS, Unidata Dataset Discovery v1.0'
             ncfile.title = 'Primary Productivity, Aqua MODIS, NPP, West Coast, EXPERIMENTAL'
             ncfile.references = 'Behrenfield and Falkowski, L&O 1997'
             ncfile.summary = 'calculates vertically integrated primary productivity using the Behrenfield - Falkowski method and satellite-based measurements of Chlorophyll a, incident visible surface irradiance, and sea surface temperature.  see (Behrenfield and Falkowski, L&O 1997).'
             ncfile.institution = "NOAA ERD"
             ncfile.contact = "http://www.pfeg.noaa.gov/guest_book.html"
             ncfile.creator_name= "NOAA PFEG"
             ncfile.creator_email="http://www.pfeg.noaa.gov/guest_book.html"
             ncfile.creation_date = str(today)
             ncfile.spatial_resolution = "0.0125 degree"
             ncfile.source_data=filenameCHLA+', '+filenamePAR+', '+filenameSSTD
             ncfile.Southernmost_Northing = 22.0
             ncfile.Northernmost_Northing = 51.0
             ncfile.Westernmost_Easting = 205.0
             ncfile.Easternmost_Easting = 255.0
             ncfile.rights = 'The data may be used and redistributed for free but is not intended for legal use, since it may contain inaccuracies. Neither the data Contributor, CoastWatch, NOAA, nor the United States Government, nor any of their employees or contractors, makes any warranty, express or implied, including warranties of merchantability and fitness for a particular purpose, or assumes any legal liability for the accuracy, completeness, or usefulness, of this information.'
             ncfile.history = "" ;
#Fill Variables
             altitude[0] = 0.
             latitude[:] = lat
             longitude[:] = lon
             primprod[:,:] = prod
             time[0]=myTime

#close ncfile
             ncfile.close()
             myCmd = '/home/rmendels/anaconda/bin/nccopy -k4 -d2 temp.nc ' + ppFile
             os.system(myCmd)
             myCmd = 'rm -f temp.nc'
             os.system(myCmd)
  DAYLEN.close()

def MHPProductivity(years):
  """Run the legacy MODIS-MH1 daily primary productivity workflow."""

  import numpy as np
  import operator
  from netCDF4 import Dataset
  import numpy.ma as ma
  import glob, os, sys

# define the data directories
  parDir = "/u00/satellite/MH1/par/1day/"
  sstDir = "/u00/satellite/MH1/sst/1day/"
  chlaDir = "/u00/satellite/MH1/chla/1day/"
  ppDir = "/u00/satellite/PP3/1day/"
#Load in daylen.nc
  DAYLEN = Dataset('worlddaylen.nc', 'r')

#Load variables lat, lon, and daylen from nc file
  lat = DAYLEN.variables['lat'][:]
  lon = DAYLEN.variables['lon'][:]
  daylen1 = DAYLEN.variables['daylen']
  lonsdim = lon.shape[0]
  latsdim = lat.shape[0]


#Loop through year and date
  for year1 in years:
      print(year1)
      year=str(year1)
      if(isleap(year1)):
          days=range(1,367)
      else:
          days=range(1,366)
      for doy in days:
          print(doy)
          day=str(doy)
          day=day.rjust(3,'0')
          temp = daylen1[doy-1,:]
          temp = np.tile(temp,(lonsdim,1))
#transpose temp to achieve correct lat lon grid of 4320, 8640
          daylen = np.transpose(temp)

#Filenames for hdf files
          filename_chl = chlaDir + 'A' + year + day + '.L3m_DAY_CHL_chlor_a_4km'
          filename_par = parDir + 'A' + year + day + '.L3m_DAY_PAR_par_4km'
          filenameSSTD = sstDir + 'A' + year + day + '.L3m_DAY_SST_4.nc'
          sstTest = os.path.isfile(filenameSSTD)
          chlaTest = os.path.isfile(filenameCHLA)
          parTest = os.path.isfile(filenamePAR)
          if (sstTest and chlaTest and parTest):

             print('found files')
#load in hdf
             chl_load = SD(filename_chl, SDC.READ)
             par_load = SD(filename_par, SDC.READ)

#read in data from hdf files for chl, par
             dataname_chl='l3m_data'
             data_chl = chl_load.select(dataname_chl)
             chl = data_chl[:,:]
             chl = ma.masked_array(chl, mask = [chl == -32767])

             dataname_par='l3m_data'
             data_par = par_load.select(dataname_par)
             par = data_par[:,:]
             par = ma.masked_array(par, mask = [par == -32767])

#create filename to load in nc file for SST

#Load NETCDF4 Files
             SSTD = Dataset(filenameSSTD, 'r')

#Pull out the variables from each file needed for production calculation
             sst = SSTD.variables['MHsstd'][:,:,:]

#Pull out data array from above variables
             sst = np.squeeze(sst)

# Calculate Productivity
             prod = BFprimprod(chl,par,sst,daylen)


# Save as netcdf
#dataset creation
             ppFile = ppDir + 'A' + year + day + '.L3m_DAY_primprod.nc'
             ncfile = Dataset('temp.nc', 'w')

#create dimensions
             latdim = ncfile.createDimension('latdim', latsdim)
             londim = ncfile.createDimension('londim', lonsdim)

#create variables
             latitude = ncfile.createVariable('lat','f4',('latdim'))
             longitude = ncfile.createVariable('lon','f4',('londim'))
             primprod = ncfile.createVariable('pprod','f4',('latdim','londim'))
             daylength = ncfile.createVariable('daylen','f4',('latdim','londim'))


#Fill Variables
             latitude[:] = lat
             longitude[:] = lon
             primprod[:,:] = prod
             daylength[:,:] = daylen


#close ncfile
             ncfile.close()
             SSTD.close()
             myCmd = '/home/rmendels/anaconda/bin/nccopy -k4 -d2 temp.nc ' + ppFile
             os.system(myCmd)
             myCmd = 'rm -f temp.nc'
             os.system(myCmd)

  DAYLEN.close()

def MHPProductivityPart(years, days):
  """Run the legacy MODIS-MH1 productivity workflow for selected days."""

  import numpy as np
  from netCDF4 import Dataset, num2date, date2num
  import numpy.ma as ma
  import glob, os, sys
  from datetime import date, datetime, timedelta
  from pyhdf.SD import SD, SDC

# define the data directories
  parDir = "/u00/satellite/MH1/par/1day/"
  sstDir = "/u00/satellite/MH1/sst/1day/"
  chlaDir = "/u00/satellite/MH1/chla/1day/"
  ppDir = "/u00/satellite/PP3/1day/"
# date for creation date
  today=date.today()
#Load in daylen.nc
  DAYLEN = Dataset('worlddaylen.nc', 'r')

#Load variables lat, lon, and daylen from nc file
  lat = DAYLEN.variables['lat'][:]
  lon = DAYLEN.variables['lon'][:]
  daylen1 = DAYLEN.variables['daylen']
  lonsdim = lon.shape[0]
  latsdim = lat.shape[0]


#Loop through year and date
  year=str(years)
  for doy in days:
          print(doy)
          myDate = datetime(years, 1, 1) + timedelta(doy-1)
          myTime = date2num(myDate,units='seconds  since 1970-01-01')
          myTime= myTime + 43200
          day=str(doy)
          day=day.rjust(3,'0')
          temp = daylen1[doy-1,:]
          temp = np.tile(temp,(lonsdim,1))
#transpose temp to achieve correct lat lon grid of 4320, 8640
          daylen = np.transpose(temp)

#Filenames for hdf files
          filename_chl = 'A' + year + day + '.L3m_DAY_CHL_chlor_a_4km'
          filename_par = 'A' + year + day + '.L3m_DAY_PAR_par_4km'
          filenameSSTD = 'A' + year + day + '.L3m_DAY_SST_4.nc'
          sstTest = os.path.isfile(sstDir+filenameSSTD)
          chlaTest = os.path.isfile(chlaDir+filename_chl)
          parTest = os.path.isfile(parDir+filename_par)
          if (sstTest and chlaTest and parTest):

             print('found files')
#load in hdf
             chl_load = SD(chlaDir+filename_chl, SDC.READ)
             par_load = SD(parDir+filename_par, SDC.READ)

#read in data from hdf files for chl, par
             dataname_chl='l3m_data'
             data_chl = chl_load.select(dataname_chl)
             chl = data_chl[:,:]
             chl = ma.masked_array(chl, mask = [chl == -32767])

             dataname_par='l3m_data'
             data_par = par_load.select(dataname_par)
             par = data_par[:,:]
             par = ma.masked_array(par, mask = [par == -32767])

#create filename to load in nc file for SST

#Load NETCDF4 Files
             SSTD = Dataset(sstDir+filenameSSTD, 'r')

#Pull out the variables from each file needed for production calculation
             sst = SSTD.variables['MHsst'][:,:,:]

#Pull out data array from above variables
             sst = np.squeeze(sst)

# Calculate Productivity
             prod = BFprimprod(chl,par,sst,daylen)
             ma.set_fill_value(prod,-99999)


# Save as netcdf
#dataset creation
             ppFile = ppDir + 'A' + year + day + '.L3m_DAY_primprod.nc'
             ncfile = Dataset('temp.nc', 'w')

#create dimensions
             latdim = ncfile.createDimension('latitude', latsdim)
             londim = ncfile.createDimension('longitude', lonsdim)
             timedim= ncfile.createDimension('time', 1)
             altitude = ncfile.createDimension('altitude', 1)

#create variables
#create variables
             latitude = ncfile.createVariable('latitude','f4',('latitude'))
             longitude = ncfile.createVariable('longitude','f4',('longitude'))
             altitude = ncfile.createVariable('altitude','f4',('altitude'))
             time = ncfile.createVariable('time','i4',('time'))
             primprod = ncfile.createVariable('MHPProd','f4',('time','altitude','latitude','longitude'),fill_value=-99999.0)
#attributes
#
#time attributes
             time.actual_range=str(myTime) + ', ' + str(myTime)
             time.long_name = 'Centered Time'
             time.units =  'seconds since 1970-01-01T00:00:00Z'
             time.standard_name = 'time'
             time.axis =  'T'
             time._CoordinateAxisType =  'Time'
#altitude attributes
             altitude.actual_range =  '0.0, 0.0'
             altitude.long_name =  'Altitude'
             altitude.positive =  'up'
             altitude.standard_name =  'altitude'
             altitude.units = 'm'
             altitude.axis =  'Z'
             altitude._CoordinateAxisType = 'Height'
             altitude._CoordinateZisPositive =  'up'
#latitude attributes
             latitude._CoordinateAxisType =  'Lat'
             latitude.actual_range =  '89.97918, -89.97918'
             latitude.coordsys = 'geographic'
             latitude.long_name = 'Latitude'
             latitude.point_spacing = 'even'
             latitude.standard_name = 'latitude'
             latitude.units = 'degrees_north'
             latitude.axis = 'Y'
#longitude attributes
             longitude._CoordinateAxisType = 'Lon'
             longitude.actual_range =  '-179.9792, 179.9792'
             longitude.coordsys =  'geographic'
             longitude.long_name =  'Longitude'
             longitude.point_spacing =  'even'
             longitude.standard_name =  'longitude'
             longitude.units =  'degrees_east'
             longitude.axis =  'X'
#primprod attributes
             primprod.coordsys =  'geographic'
             primprod.long_name =  'Primary Productivity, Aqua MODIS L3M, NPP, Global, EXPERIMENTAL'
             primprod.missing_value =  -99999.0
             primprod.standard_name =  'net_primary_productivity_of_carbon'
             primprod.units = 'mg C m-2 day-1'
#  global attributes
             ncfile.Conventions = 'CF-1.6, COARDS, Unidata Dataset Discovery v1.0'
             ncfile.title = 'Primary Productivity, Aqua MODIS, NPP, West Coast, EXPERIMENTAL'
             ncfile.references = 'Behrenfield and Falkowski, L&O 1997'
             ncfile.summary = 'calculates vertically integrated primary productivity using the Behrenfield - Falkowski method and satellite-based measurements of Chlorophyll a, incident visible surface irradiance, and sea surface temperature.  see (Behrenfield and Falkowski, L&O 1997).'
             ncfile.institution = "NOAA ERD"
             ncfile.contact = "http://www.pfeg.noaa.gov/guest_book.html"
             ncfile.creator_name= "NOAA PFEG"
             ncfile.creator_email="http://www.pfeg.noaa.gov/guest_book.html"
             ncfile.creation_date = str(today)
             ncfile.spatial_resolution = "0.0417 degree"
             ncfile.source_data=filename_chl+', '+filename_par+', '+filenameSSTD
             ncfile.Southernmost_Northing = -89.97918
             ncfile.Northernmost_Northing = 89.97918
             ncfile.Westernmost_Easting = -179.9792
             ncfile.Easternmost_Easting = 179.9792
             ncfile.rights = 'The data may be used and redistributed for free but is not intended for legal use, since it may contain inaccuracies. Neither the data Contributor, CoastWatch, NOAA, nor the United States Government, nor any of their employees or contractors, makes any warranty, express or implied, including warranties of merchantability and fitness for a particular purpose, or assumes any legal liability for the accuracy, completeness, or usefulness, of this information.'
             ncfile.history = "" ;


#Fill Variables
             altitude[0] = 0.
             latitude[:] = lat
             longitude[:] = lon
             primprod[:,:] = prod
             time[0]=myTime

#close ncfile
             ncfile.close()
             SSTD.close()
             myCmd = '/home/rmendels/anaconda/bin/nccopy -k4 -d2 temp.nc ' + ppFile
             os.system(myCmd)
             myCmd = 'rm -f temp.nc'
             os.system(myCmd)

  DAYLEN.close()

def MWPProductivityPart(years,days):
  """Run the legacy MODIS-West productivity workflow for selected days."""

  import numpy as np
  import operator
  from netCDF4 import Dataset, num2date, date2num
  import numpy.ma as ma
  import glob, os, sys
  from datetime import date, datetime, timedelta
# define the data directories
  parDir = "/u00/satellite/MW/par0/1day/"
  sstDir = "/u00/satellite/MW/sstd/1day/"
  chlaDir = "/u00/satellite/MW/chla/1day/"
  ppDir = "/u00/satellite/PP2/1day/"
# date for creation date
  today=date.today()
#Load in daylen.nc
  DAYLEN = Dataset('daylen.nc', 'r', format='NETCDF3_CLASSIC')

#Load variables lat, lon, and daylen from nc file
  lat = DAYLEN.variables['lat'][:]
  lon = DAYLEN.variables['lon'][:]
  daylen1 = DAYLEN.variables['daylen']


#Loop through year and date
  year=str(years)
  for doy in days:
          print(doy)
          myDate = datetime(years, 1, 1) + timedelta(doy-1)
          myTime = date2num(myDate,units='seconds  since 1970-01-01')
          myTime= myTime + 43200
          day=str(doy)
          day=day.rjust(3,'0')
          daylen = daylen1[doy-1,:,:]

          filenameSSTD = 'MW' + year + day + '_' + year + day + '_sstd.nc'
          filenamePAR  ='MW' + year + day + '_' + year + day + '_par0.nc'
          filenameCHLA = 'MW' + year + day + '_' + year + day + '_chla.nc'

# Load NETCDF4 Files
          sstTest = os.path.isfile(sstDir+filenameSSTD)
          chlaTest = os.path.isfile(chlaDir+filenameCHLA)
          parTest = os.path.isfile(parDir+filenamePAR)
          if (sstTest and chlaTest and parTest):
             print('found files')
             SSTD = Dataset(sstDir+filenameSSTD, 'r')
             PAR  = Dataset(parDir+filenamePAR, 'r')
             CHLA = Dataset(chlaDir+filenameCHLA, 'r')


#Pull out the variables from each file needed for production calculation
             sst = SSTD.variables['MWsstd'][:,:,:,:]
             par = PAR.variables['MWpar0'][:,:,:,:]
             chl = CHLA.variables['MWchla'][:,:,:,:]


#Pull out data array from above variables
             sst = np.squeeze(sst)
             par = np.squeeze(par)
             chl = np.squeeze(chl)

# Calculate Productivity
             prod = BFprimprod(chl,par,sst,daylen)
             ma.set_fill_value(prod,-99999)

# Save as netcdf
#create dimensions for prod
             latsdim = lat.shape[0]
             lonsdim = lon.shape[0]


#dataset creation
             ppFile = ppDir + 'MWPrimProd' + year + day + '_' + year + day + '.nc'
             ncfile = Dataset('temp.nc', 'w')

#create dimensions
             latdim = ncfile.createDimension('latitude', latsdim)
             londim = ncfile.createDimension('longitude', lonsdim)
             timedim= ncfile.createDimension('time', 1)
             altitude = ncfile.createDimension('altitude', 1)

#create variables
             latitude = ncfile.createVariable('latitude','f4',('latitude'))
             longitude = ncfile.createVariable('longitude','f4',('longitude'))
             altitude = ncfile.createVariable('altitude','f4',('altitude'))
             time = ncfile.createVariable('time','i4',('time'))
             primprod = ncfile.createVariable('MWPProd','f4',('time','altitude','latitude','longitude'),fill_value=-99999.0)
#attributes
#
#time attributes
             time.actual_range=str(myTime) + ', ' + str(myTime)
             time.long_name = 'Centered Time'
             time.units =  'seconds since 1970-01-01T00:00:00Z'
             time.standard_name = 'time'
             time.axis =  'T'
             time._CoordinateAxisType =  'Time'
#altitude attributes
             altitude.actual_range =  '0.0, 0.0'
             altitude.long_name =  'Altitude'
             altitude.positive =  'up'
             altitude.standard_name =  'altitude'
             altitude.units = 'm'
             altitude.axis =  'Z'
             altitude._CoordinateAxisType = 'Height'
             altitude._CoordinateZisPositive =  'up'
#latitude attributes
             latitude._CoordinateAxisType =  'Lat'
             latitude.actual_range =  '22.0, 51.0'
             latitude.coordsys = 'geographic'
             latitude.long_name = 'Latitude'
             latitude.point_spacing = 'even'
             latitude.standard_name = 'latitude'
             latitude.units = 'degrees_north'
             latitude.axis = 'Y'
#longitude attributes
             longitude._CoordinateAxisType = 'Lon'
             longitude.actual_range =  '205.0, 255.0'
             longitude.coordsys =  'geographic'
             longitude.long_name =  'Longitude'
             longitude.point_spacing =  'even'
             longitude.standard_name =  'longitude'
             longitude.units =  'degrees_east'
             longitude.axis =  'X'
#primprod attributes
             primprod.coordsys =  'geographic'
             primprod.long_name =  'Primary Productivity, Aqua MODIS, NPP, West Coast, EXPERIMENTAL'
             primprod.missing_value =  -99999.0
             primprod.standard_name =  'net_primary_productivity_of_carbon'
             primprod.units = 'mg C m-2 day-1'
#  global attributes
             ncfile.Conventions = 'CF-1.6, COARDS, Unidata Dataset Discovery v1.0'
             ncfile.title = 'Primary Productivity, Aqua MODIS, NPP, West Coast, EXPERIMENTAL'
             ncfile.references = 'Behrenfield and Falkowski, L&O 1997'
             ncfile.summary = 'calculates vertically integrated primary productivity using the Behrenfield - Falkowski method and satellite-based measurements of Chlorophyll a, incident visible surface irradiance, and sea surface temperature.  see (Behrenfield and Falkowski, L&O 1997).'
             ncfile.institution = "NOAA ERD"
             ncfile.contact = "http://www.pfeg.noaa.gov/guest_book.html"
             ncfile.creator_name= "NOAA PFEG"
             ncfile.creator_email="http://www.pfeg.noaa.gov/guest_book.html"
             ncfile.creation_date = str(today)
             ncfile.spatial_resolution = "0.0125 degree"
             ncfile.source_data=filenameCHLA+', '+filenamePAR+', '+filenameSSTD
             ncfile.Southernmost_Northing = 22.0
             ncfile.Northernmost_Northing = 51.0
             ncfile.Westernmost_Easting = 205.0
             ncfile.Easternmost_Easting = 255.0
             ncfile.rights = 'The data may be used and redistributed for free but is not intended for legal use, since it may contain inaccuracies. Neither the data Contributor, CoastWatch, NOAA, nor the United States Government, nor any of their employees or contractors, makes any warranty, express or implied, including warranties of merchantability and fitness for a particular purpose, or assumes any legal liability for the accuracy, completeness, or usefulness, of this information.'
             ncfile.history = "" ;
#Fill Variables
             altitude[0] = 0.
             latitude[:] = lat
             longitude[:] = lon
             primprod[:,:] = prod
             time[0]=myTime

#close ncfile
             ncfile.close()
             myCmd = '/home/rmendels/anaconda/bin/nccopy -k4 -d2 temp.nc ' + ppFile
             os.system(myCmd)
             myCmd = 'rm -f temp.nc'
             os.system(myCmd)
  DAYLEN.close()
