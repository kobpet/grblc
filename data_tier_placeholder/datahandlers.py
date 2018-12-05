from abc import ABC
from data_tier_placeholder.skyobject import SkyObject
from data_tier_placeholder.image import Image
import glob
import pyfits
import sys
import os
from astroquery.vizier import Vizier

import astropy.units as u
import astropy.coordinates as coord


class InvalidQueryError(Exception):
    pass


class DataManagerFactory:
    """
    Factory class for selecting desired handlers based on path and query type.
    """
    @staticmethod
    def get_handler(path: str, query: str=None):
        """
        Supplies handler based on type of path:
        "sqlite:" gets database handler with path to it given db file (e.g.  sqlite:/tmp/temp.db)
        "/tmp/"   gets file handler with getting all files in a folder restricted by query
        "/tmp/file.fits" gets file handler for single file
        query format: shell regex with space delimiter for additional type specification
        :param path:
        :param query: a query string in format "regex type_specification" for example "*df.fits data"
        :return: a handler for type of path and query
        """
        pass
        # TODO add allowed type options (data/flat/dark/  possibly - grb/star)


class BasicHandler(ABC):

    def __init__(self, path: str, query: str=None):
        self.query = query
        self.path = path

    def get_list(self):
        """returns list of objects based on selected handler and query"""
        raise NotImplementedError


class FileHandler(BasicHandler):
    """
    Handler for file and folder type queries.
    Only allows generation of lists of images and single image objects
    Examples of usage:
        getting an image list of corrected images:

            image_list = FileHandler("folder_path/", "*.fits cdata").get_list()
                - returns image_list of all fits files in specified folder

        getting an image list of flat images:

            image_list = FileHandler("flat_folder_path/", "*.fits flat")
                - returns image_list of flat type image objects

        getting a single image object:
            image = FileHandler("file_path/image.fits", "data")

            or

            image = FileHandler("file_path/", "image.fits data")

                -both return an Image type object of with specified path and data type

    Allowed data types in query parameter:
        flat - flat field images
        dark - dark images
        data - non-corrected (no dark current or flat field correction) images
        ddata - dark corrected images
        dfdata, cdata = dark and flat corrected data or otherwise corrected images used straight for photometry

    Query format:
        - query must always contain data type
        - folder queries must always contain data type AND filter for selecting files in folder (minimum is
            an asterisk *)
        - queries for single file can be done either by specifiyng file in path and using only data type query or
            specifying path of folder and then using query with filename and data type

        Examples:
            "*df.fits cdata"
            "* cdata"
            "flat"
            "flat.fits flat"
    """

    def __init__(self, path: str, query: str):
        super().__init__(path, query)
        squery = query.split(" ")
        if len(squery) == 2:  # Query + data type
            self.query = squery[0]
            if True in [data_type in squery[1] for data_type in ["flat", "dark", "data", "ddata", "cdata", "dfdata"]]:
                self.type = squery[1]
            else:  # data type is not in legal ones
                raise InvalidQueryError("invalid data type")
        else:  # Selecting single file, only data type necessary
            if True in [data_type in squery[0] for data_type in ["flat", "dark", "data", "ddata", "cdata", "dfdata"]]:
                self.query = ""
                self.type = squery[0]
            else:
                raise InvalidQueryError("invalid data type")

    def get_list(self):
        gstring = self.path + self.query
        # decide data type and corrections
        if self.type == "flat" or self.type == "dark" or self.type == "data":
            data_type = self.type
            processing_pars = {}
        elif self.type == "cdata" or self.type == "dfdata":
            data_type = "data"
            processing_pars = {"flat": True, "dark": True}
        else:
            data_type = "data"
            processing_pars = {"dark": True}

        image_list = []
        k = 0
        if len(glob.glob(gstring)) > 1:
            for path in glob.glob(gstring):
                image = pyfits.open(path)
                exposure = image[0].header["EXPOSURE"]
                time_jd = image[0].header["JD"]
                fixed_pars = {
                    "time_jd": time_jd,
                    "path": path,
                    "type": data_type,
                    "exposure": exposure,
                    "id": k}
                image_list.append(Image(fixed_parameters=fixed_pars,
                                        processing_parameters=processing_pars))
                k += 1
        elif len(glob.glob(gstring)) == 0:
            raise InvalidQueryError("no images fit query")
        else:
            image = pyfits.open(gstring)
            exposure = image[0].header["EXPOSURE"]
            time_jd = image[0].header["JD"]
            fixed_pars = {
                "time_jd": time_jd,
                "path": gstring,
                "type": data_type,
                "exposure": exposure,
                "id": k}
            image_list = Image(fixed_parameters=fixed_pars,
                               processing_parameters=processing_pars)
            # TODO Decide whether to return list or single object if only one image matches query
        return image_list


class DatabaseHandler(BasicHandler):
    """
    Handler for interacting with database (sqlite3)
    Allows loading and saving images and object data from database file.
    """
    def __init__(self, path: str, query: str=None):
        super().__init__(query, path)

    def get_list(self):
        pass
    # TODO

    @staticmethod
    def save_objects_and_images(image_list: [Image], object_list: [SkyObject]):
        """Saving to database file using SQL Alchemy"""
        pass
    # TODO


class ObjectHandler:
    """Handler to create list of objects in specified vicinity of given target

    Supported catalogues:
        APASS
        NOMAD

    Usage:
        If not specified the default values for area around target coordinates are:
            radius = 0.1 degrees
            catalog: APASS
            lower magnitude limit: 16 mag
            maximum objects is 100

        Initialize with target object (GRB) and specify result limit if necessary. You can change default values in
        get_list() call as follows:

            ObjectHandler(target).get_list(mag_limit = 20, catalog= "NOMAD", radius = 2 * u.deg)

         * - Units for radius are in degrees

    """
    # TODO Static methods?

    def __init__(self, target: SkyObject, result_limit=100):
        self.target = target
        self.limit = result_limit

    def get_list(self, mag_limit=16., catalog="APASS", radius=0.1,):
        """

        :param mag_limit: float
        :param catalog: catalog name string
        :param radius: radius in degrees
        :return: Object type list with target and objects in specified vicinity
        """
        if catalog == "APASS":
            return self.vizier_query_object_list_apass(self.target, radius, mag_limit)
        if catalog == "NOMAD":
            return self.vizier_query_object_list_nomad(self.target, radius, mag_limit)
        else:
            raise ValueError("Unsupported or invalid catalogue name")

    def vizier_query_object_list_apass(self, target: SkyObject, radius, mag_limit):
        """
        Creates object list from vizier APASS query

        :param target: Center point around which to query for object
        :param radius: radius of area around central object in degrees
        :param mag_limit: limiting lower magnitude for star selection
        :return: list of objects and the GRB
        """
        vizier_query = Vizier(columns=['RAJ2000', 'DEJ2000', 'Vmag','e_Vmag'],
                              column_filters={"Vmag": "<"+str(mag_limit)},
                              row_limit= self.limit)
        coordinates = coord.SkyCoord(target.fixed_parameters["ra"],
                                     target.fixed_parameters["dec"],
                                     unit=(u.deg, u.deg),
                                     frame='icrs')
        result = vizier_query.query_region(coordinates,
                                           radius=radius * u.deg,
                                           catalog="APASS")

        object_list = [target]
        i = 1
        for o in result[0]:
            object_list.append(SkyObject({"ra": o['RAJ2000'],
                                          "dec": o['DEJ2000'],
                                          "catalog_magnitude": (o['Vmag'], o['e_Vmag']),
                                          "id": i,
                                          "type": "star"}))
            i += 1

        return object_list

    def vizier_query_object_list_nomad(self, target: SkyObject, radius, mag_limit):
        """
        Creates object list from vizier NOMAD query

        :param target: Center point around which to query for object
        :param radius: radius of area around central object in degrees
        :param mag_limit: limiting lower magnitude for star selection
        :return: list of objects and the GRB
        """
        vizier_query = Vizier(columns=['RAJ2000', 'DEJ2000', 'Vmag'],
                              column_filters={"Vmag": "<"+str(mag_limit)},
                              row_limit=self.limit)
        coordinates = coord.SkyCoord(target.fixed_parameters["ra"],
                                     target.fixed_parameters["dec"],
                                     unit=(u.deg, u.deg),
                                     frame='icrs')
        result = vizier_query.query_region(coordinates,
                                           radius=radius * u.deg,
                                           catalog="NOMAD")

        object_list = [target]
        i = 1
        for o in result[0]:
            object_list.append(SkyObject({"ra": o['RAJ2000'],
                                          "dec": o['DEJ2000'],
                                          "catalog_magnitude": (o['Vmag'], o['e_Vmag']),
                                          "id": i,
                                          "type": "star"}))
            i += 1

        return object_list
