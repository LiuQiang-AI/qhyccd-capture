from .language import translations

global language
language = 'en'

def get_header_defaults(language):
    # 使用当前的语言设置来构建字典
    default_keys = [
        ("SIMPLE", translations[language]["fits_header_defaults"]["standard"]),
        ("BITPIX", translations[language]["fits_header_defaults"]["data_type"]),
        ("NAXIS", translations[language]["fits_header_defaults"]["array_dimensions"]),
        ("NAXIS1", translations[language]["fits_header_defaults"]["axis_length"] + " 1"),
        ("NAXIS2", translations[language]["fits_header_defaults"]["axis_length"] + " 2"),
        ("EXTEND", translations[language]["fits_header_defaults"]["extensions"]),
        ("BZERO", translations[language]["fits_header_defaults"]["scaling_zero"]),
        ("BSCALE", translations[language]["fits_header_defaults"]["scaling_factor"]),
        ("DATE-OBS", translations[language]["fits_header_defaults"]["observation_date"]),
        ("EXPTIME", translations[language]["fits_header_defaults"]["exposure_time"]),
        ("TELESCOP", translations[language]["fits_header_defaults"]["telescope"]),
        ("INSTRUME", translations[language]["fits_header_defaults"]["instrument"]),
        ("OBSERVER", translations[language]["fits_header_defaults"]["observer"]),
        ("OBJECT", translations[language]["fits_header_defaults"]["observed_object"]),
        ("RA", translations[language]["fits_header_defaults"]["celestial_coordinate"]),
        ("DEC", translations[language]["fits_header_defaults"]["celestial_coordinate"]),  
        ("EQUINOX", translations[language]["fits_header_defaults"]["equinox"]),
        ("FILTER", translations[language]["fits_header_defaults"]["filter"]),
        ("AIRMASS", translations[language]["fits_header_defaults"]["airmass"]),
        ("LST", translations[language]["fits_header_defaults"]["sidereal_time"]),
        ("GAIN", translations[language]["fits_header_defaults"]["detector_gain"]),
        ("READNOIS", translations[language]["fits_header_defaults"]["read_noise"]),
        ("CD1_1", translations[language]["fits_header_defaults"]["transformation_matrix"]),
        ("CD1_2", translations[language]["fits_header_defaults"]["transformation_matrix"]),
        ("CD2_1", translations[language]["fits_header_defaults"]["transformation_matrix"]),
        ("CD2_2", translations[language]["fits_header_defaults"]["transformation_matrix"]),
        ("CTYPE1", translations[language]["fits_header_defaults"]["coordinate_type"] + " in axis 1"),
        ("CTYPE2", translations[language]["fits_header_defaults"]["coordinate_type"] + " in axis 2"),
        ("CRPIX1", translations[language]["fits_header_defaults"]["reference_pixel"] + " in axis 1"),
        ("CRPIX2", translations[language]["fits_header_defaults"]["reference_pixel"] + " in axis 2"),
        ("CRVAL1", translations[language]["fits_header_defaults"]["coordinate_value"] + " in axis 1"),
        ("CRVAL2", translations[language]["fits_header_defaults"]["coordinate_value"] + " in axis 2"),
        ("CUNIT1", translations[language]["fits_header_defaults"]["coordinate_units"] + " in axis 1"),
        ("CUNIT2", translations[language]["fits_header_defaults"]["coordinate_units"] + " in axis 2"),
        ("COMMENT", translations[language]["fits_header_defaults"]["general_comment"]),
        ("HISTORY", translations[language]["fits_header_defaults"]["processing_history"])
    ]
    return {key: desc for key, desc in default_keys}

