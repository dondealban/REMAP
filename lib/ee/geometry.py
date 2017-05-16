#!/usr/bin/env python
"""An object representing EE Geometries."""



# Using lowercase function naming to match the JavaScript names.
# pylint: disable=g-bad-name

import collections
import json
import numbers

import apifunction
import computedobject
import ee_exception
import ee_types
import serializer


# A sentinel value used to detect unspecified function parameters.
_UNSPECIFIED = object()


class Geometry(computedobject.ComputedObject):
  """An Earth Engine geometry."""

  _initialized = False

  def __init__(self, geo_json, opt_proj=None, opt_geodesic=None):
    """Creates a geometry.

    Args:
      geo_json: The GeoJSON object describing the geometry or a
          computed object to be reinterpred as a Geometry. Supports
          CRS specifications as per the GeoJSON spec, but only allows named
          (rather than "linked" CRSs). If this includes a 'geodesic' field,
          and opt_geodesic is not specified, it will be used as opt_geodesic.
      opt_proj: An optional projection specification, either as an
          ee.Projection, as a CRS ID code or as a WKT string. If specified,
          overrides any CRS found in the geo_json parameter. If unspecified and
          the geo_json does not declare a CRS, defaults to "EPSG:4326"
          (x=longitude, y=latitude).
      opt_geodesic: Whether line segments should be interpreted as spherical
          geodesics. If false, indicates that line segments should be
          interpreted as planar lines in the specified CRS. If absent,
          defaults to true if the CRS is geographic (including the default
          EPSG:4326), or to false if the CRS is projected.

    Raises:
      EEException: if the given geometry isn't valid.
    """
    self.initialize()

    computed = (isinstance(geo_json, computedobject.ComputedObject) and
                not (isinstance(geo_json, Geometry) and
                     geo_json._type is not None))  # pylint: disable=protected-access
    options = opt_proj or opt_geodesic
    if computed:
      if options:
        raise ee_exception.EEException(
            'Setting the CRS or geodesic on a computed Geometry is not '
            'suported.  Use Geometry.transform().')
      else:
        super(Geometry, self).__init__(
            geo_json.func, geo_json.args, geo_json.varName)
        return

    # Below here we're working with a GeoJSON literal.
    if isinstance(geo_json, Geometry):
      geo_json = geo_json.encode()

    if not Geometry._isValidGeometry(geo_json):
      raise ee_exception.EEException('Invalid GeoJSON geometry.')

    super(Geometry, self).__init__(None, None)

    # The type of the geometry.
    self._type = geo_json['type']

    # The coordinates of the geometry, up to 4 nested levels with numbers at
    # the last level. None iff type is GeometryCollection.
    self._coordinates = geo_json.get('coordinates')

    # The subgeometries, None unless type is GeometryCollection.
    self._geometries = geo_json.get('geometries')

    # The projection code (WKT or identifier) of the geometry.
    if opt_proj:
      self._proj = opt_proj
    elif 'crs' in geo_json:
      if (isinstance(geo_json.get('crs'), dict) and
          geo_json['crs'].get('type') == 'name' and
          isinstance(geo_json['crs'].get('properties'), dict) and
          isinstance(geo_json['crs']['properties'].get('name'), basestring)):
        self._proj = geo_json['crs']['properties']['name']
      else:
        raise ee_exception.EEException('Invalid CRS declaration in GeoJSON: ' +
                                       json.dumps(geo_json['crs']))
    else:
      self._proj = None

    # Whether the geometry has spherical geodesic edges.
    self._geodesic = opt_geodesic
    if opt_geodesic is None and 'geodesic' in geo_json:
      self._geodesic = bool(geo_json['geodesic'])

  @classmethod
  def initialize(cls):
    """Imports API functions to this class."""
    if not cls._initialized:
      apifunction.ApiFunction.importApi(cls, 'Geometry', 'Geometry')
      cls._initialized = True

  @classmethod
  def reset(cls):
    """Removes imported API functions from this class."""
    apifunction.ApiFunction.clearApi(cls)
    cls._initialized = False

  def __getitem__(self, key):
    """Allows access to GeoJSON properties for backward-compatibility."""
    return self.toGeoJSON()[key]

  @staticmethod
  def Point(coords=_UNSPECIFIED, proj=_UNSPECIFIED, *args, **kwargs):
    """Constructs an ee.Geometry describing a point.

    Args:
      coords: A list of two [x,y] coordinates in the given projection.
      proj: The projection of this geometry, or EPSG:4326 if unspecified.
      *args: For convenience, varargs may be used when all arguments are
          numbers. This allows creating EPSG:4326 points, e.g.
          ee.Geometry.Point(lng, lat).
      **kwargs: Keyword args that accept "lon" and "lat" for backward-
          compatibility.

    Returns:
      An ee.Geometry describing a point.
    """
    init = Geometry._parseArgs('Point', 1, Geometry._GetSpecifiedArgs(
        (coords, proj) + args, ('lon', 'lat'), **kwargs))
    if not isinstance(init, computedobject.ComputedObject):
      xy = init['coordinates']
      if not isinstance(xy, (list, tuple)) or len(xy) != 2:
        raise ee_exception.EEException(
            'The Geometry.Point constructor requires 2 coordinates.')
    return Geometry(init)

  @staticmethod
  def MultiPoint(coords=_UNSPECIFIED, proj=_UNSPECIFIED, *args):
    """Constructs an ee.Geometry describing a MultiPoint.

    Args:
      coords: A list of points, each in the GeoJSON 'coordinates' format of a
          Point, or a list of the x,y coordinates in the given projection, or
          an ee.Geometry describing a point.
      proj: The projection of this geometry. If unspecified, the default is
          the projection of the input ee.Geometry, or EPSG:4326 if there are
          no ee.Geometry inputs.
      *args: For convenience, varargs may be used when all arguments are
          numbers. This allows creating EPSG:4326 MultiPoints given an even
          number of arguments, e.g.
          ee.Geometry.MultiPoint(aLng, aLat, bLng, bLat, ...).

    Returns:
      An ee.Geometry describing a MultiPoint.
    """
    all_args = Geometry._GetSpecifiedArgs((coords, proj) + args)
    return Geometry(Geometry._parseArgs('MultiPoint', 2, all_args))

  @staticmethod
  def Rectangle(coords=_UNSPECIFIED, proj=_UNSPECIFIED,
                geodesic=_UNSPECIFIED, maxError=_UNSPECIFIED,
                *args, **kwargs):
    """Constructs an ee.Geometry describing a rectangular polygon.

    Args:
      coords: The minimum and maximum corners of the rectangle, as a list of
          two points each in the format of GeoJSON 'Point' coordinates, or a
          list of two ee.Geometry describing a point, or a list of four
          numbers in the order xMin, yMin, xMax, yMax.
      proj: The projection of this geometry. If unspecified, the default is the
          projection of the input ee.Geometry, or EPSG:4326 if there are no
          ee.Geometry inputs.
      geodesic: If false, edges are straight in the projection. If true, edges
          are curved to follow the shortest path on the surface of the Earth.
          The default is the geodesic state of the inputs, or true if the
          inputs are numbers.
      maxError: Max error when input geometry must be reprojected to an
          explicitly requested result projection or geodesic state.
      *args: For convenience, varargs may be used when all arguments are
          numbers. This allows creating EPSG:4326 Polygons given exactly four
          coordinates, e.g.
          ee.Geometry.Rectangle(minLng, minLat, maxLng, maxLat).
      **kwargs: Keyword args that accept "xlo", "ylo", "xhi" and "yhi" for
          backward-compatibility.

    Returns:
      An ee.Geometry describing a rectangular polygon.
    """
    init = Geometry._parseArgs('Rectangle', 2, Geometry._GetSpecifiedArgs(
        (coords, proj, geodesic, maxError) + args,
        ('xlo', 'ylo', 'xhi', 'yhi'), **kwargs))
    if not isinstance(init, computedobject.ComputedObject):
      # GeoJSON does not have a Rectangle type, so expand to a Polygon.
      xy = init['coordinates']
      if not isinstance(xy, (list, tuple)) or len(xy) != 2:
        raise ee_exception.EEException(
            'The Geometry.Rectangle constructor requires 2 points or 4 '
            'coordinates.')
      x1 = xy[0][0]
      y1 = xy[0][1]
      x2 = xy[1][0]
      y2 = xy[1][1]
      init['coordinates'] = [[[x1, y2], [x1, y1], [x2, y1], [x2, y2]]]
      init['type'] = 'Polygon'
    return Geometry(init)

  @staticmethod
  def LineString(coords=_UNSPECIFIED, proj=_UNSPECIFIED,
                 geodesic=_UNSPECIFIED, maxError=_UNSPECIFIED,
                 *args):
    """Constructs an ee.Geometry describing a LineString.

    Args:
      coords: A list of at least two points.  May be a list of coordinates in
          the GeoJSON 'LineString' format, a list of at least two ee.Geometry
          describing a point, or a list of at least four numbers defining the
          [x,y] coordinates of at least two points.
      proj: The projection of this geometry. If unspecified, the default is the
          projection of the input ee.Geometry, or EPSG:4326 if there are no
          ee.Geometry inputs.
      geodesic: If false, edges are straight in the projection. If true, edges
          are curved to follow the shortest path on the surface of the Earth.
          The default is the geodesic state of the inputs, or true if the
          inputs are numbers.
      maxError: Max error when input geometry must be reprojected to an
          explicitly requested result projection or geodesic state.
      *args: For convenience, varargs may be used when all arguments are
          numbers. This allows creating geodesic EPSG:4326 LineStrings given
          an even number of arguments, e.g.
          ee.Geometry.LineString(aLng, aLat, bLng, bLat, ...).

    Returns:
      An ee.Geometry describing a LineString.
    """
    all_args = Geometry._GetSpecifiedArgs(
        (coords, proj, geodesic, maxError) + args)
    return Geometry(Geometry._parseArgs('LineString', 2, all_args))

  @staticmethod
  def LinearRing(coords=_UNSPECIFIED, proj=_UNSPECIFIED,
                 geodesic=_UNSPECIFIED, maxError=_UNSPECIFIED,
                 *args):
    """Constructs an ee.Geometry describing a LinearRing.

    If the last point is not equal to the first, a duplicate of the first
    point will be added at the end.

    Args:
      coords: A list of points in the ring. May be a list of coordinates in
          the GeoJSON 'LinearRing' format, a list of at least three ee.Geometry
          describing a point, or a list of at least six numbers defining the
          [x,y] coordinates of at least three points.
      proj: The projection of this geometry. If unspecified, the default is the
          projection of the input ee.Geometry, or EPSG:4326 if there are no
          ee.Geometry inputs.
      geodesic: If false, edges are straight in the projection. If true, edges
          are curved to follow the shortest path on the surface of the Earth.
          The default is the geodesic state of the inputs, or true if the
          inputs are numbers.
      maxError: Max error when input geometry must be reprojected to an
          explicitly requested result projection or geodesic state.
      *args: For convenience, varargs may be used when all arguments are
          numbers. This allows creating geodesic EPSG:4326 LinearRings given
          an even number of arguments, e.g.
          ee.Geometry.LinearRing(aLng, aLat, bLng, bLat, ...).

    Returns:
      A dictionary representing a GeoJSON LinearRing.
    """
    all_args = Geometry._GetSpecifiedArgs(
        (coords, proj, geodesic, maxError) + args)
    return Geometry(Geometry._parseArgs('LinearRing', 2, all_args))

  @staticmethod
  def MultiLineString(coords=_UNSPECIFIED, proj=_UNSPECIFIED,
                      geodesic=_UNSPECIFIED, maxError=_UNSPECIFIED,
                      *args):
    """Constructs an ee.Geometry describing a MultiLineString.

    Create a GeoJSON MultiLineString from either a list of points, or an array
    of lines (each an array of Points).  If a list of points is specified,
    only a single line is created.

    Args:
      coords: A list of linestrings. May be a list of coordinates in the
          GeoJSON 'MultiLineString' format, a list of at least two ee.Geometry
          describing a LineString, or a list of number defining a single
          linestring.
      proj: The projection of this geometry. If unspecified, the default is the
          projection of the input ee.Geometry, or EPSG:4326 if there are no
          ee.Geometry inputs.
      geodesic: If false, edges are straight in the projection. If true, edges
          are curved to follow the shortest path on the surface of the Earth.
          The default is the geodesic state of the inputs, or true if the
          inputs are numbers.
      maxError: Max error when input geometry must be reprojected to an
          explicitly requested result projection or geodesic state.
      *args: For convenience, varargs may be used when all arguments are
          numbers. This allows creating geodesic EPSG:4326 MultiLineStrings
          with a single LineString, given an even number of arguments, e.g.
          ee.Geometry.MultiLineString(aLng, aLat, bLng, bLat, ...).

    Returns:
      An ee.Geometry describing a MultiLineString.
    """
    all_args = Geometry._GetSpecifiedArgs(
        (coords, proj, geodesic, maxError) + args)
    return Geometry(Geometry._parseArgs('MultiLineString', 3, all_args))

  @staticmethod
  def Polygon(coords=_UNSPECIFIED, proj=_UNSPECIFIED,
              geodesic=_UNSPECIFIED, maxError=_UNSPECIFIED,
              *args):
    """Constructs an ee.Geometry describing a polygon.

    Args:
      coords: A list of rings defining the boundaries of the polygon. May be a
          list of coordinates in the GeoJSON 'Polygon' format, a list of
          ee.Geometry describing a LinearRing, or a list of number defining a
          single polygon boundary.
      proj: The projection of this geometry. If unspecified, the default is the
          projection of the input ee.Geometry, or EPSG:4326 if there are no
          ee.Geometry inputs.
      geodesic: If false, edges are straight in the projection. If true, edges
          are curved to follow the shortest path on the surface of the Earth.
          The default is the geodesic state of the inputs, or true if the
          inputs are numbers.
      maxError: Max error when input geometry must be reprojected to an
          explicitly requested result projection or geodesic state.
      *args: For convenience, varargs may be used when all arguments are
          numbers. This allows creating geodesic EPSG:4326 Polygons with a
          single LinearRing given an even number of arguments, e.g.
          ee.Geometry.Polygon(aLng, aLat, bLng, bLat, ..., aLng, aLat).

    Returns:
      An ee.Geometry describing a polygon.
    """
    all_args = Geometry._GetSpecifiedArgs(
        (coords, proj, geodesic, maxError) + args)
    return Geometry(Geometry._parseArgs('Polygon', 3, all_args))

  @staticmethod
  def MultiPolygon(coords=_UNSPECIFIED, proj=_UNSPECIFIED,
                   geodesic=_UNSPECIFIED, maxError=_UNSPECIFIED,
                   *args):
    """Constructs an ee.Geometry describing a MultiPolygon.

    If created from points, only one polygon can be specified.

    Args:
      coords: A list of polygons. May be a list of coordinates in the GeoJSON
          'MultiPolygon' format, a list of ee.Geometry describing a Polygon,
          or a list of number defining a single polygon boundary.
      proj: The projection of this geometry. If unspecified, the default is the
          projection of the input ee.Geometry, or EPSG:4326 if there are no
          ee.Geometry inputs.
      geodesic: If false, edges are straight in the projection. If true, edges
          are curved to follow the shortest path on the surface of the Earth.
          The default is the geodesic state of the inputs, or true if the
          inputs are numbers.
      maxError: Max error when input geometry must be reprojected to an
          explicitly requested result projection or geodesic state.
      *args: For convenience, varargs may be used when all arguments are
          numbers. This allows creating geodesic EPSG:4326 MultiPolygons with
          a single Polygon with a single LinearRing given an even number of
          arguments, e.g.
          ee.Geometry.MultiPolygon(aLng, aLat, bLng, bLat, ..., aLng, aLat).

    Returns:
      An ee.Geometry describing a MultiPolygon.
    """
    all_args = Geometry._GetSpecifiedArgs(
        (coords, proj, geodesic, maxError) + args)
    return Geometry(Geometry._parseArgs('MultiPolygon', 4, all_args))

  def encode(self, opt_encoder=None):  # pylint: disable=unused-argument
    """Returns a GeoJSON-compatible representation of the geometry."""
    if not getattr(self, '_type', None):
      return super(Geometry, self).encode(opt_encoder)

    result = {'type': self._type}
    if self._type == 'GeometryCollection':
      result['geometries'] = self._geometries
    else:
      result['coordinates'] = self._coordinates

    if self._proj is not None:
      result['crs'] = {
          'type': 'name',
          'properties': {
              'name': self._proj
          }
      }

    if self._geodesic is not None:
      result['geodesic'] = self._geodesic

    return result

  def toGeoJSON(self):
    """Returns a GeoJSON representation of the geometry."""
    if self.func:
      raise ee_exception.EEException(
          'Can\'t convert a computed geometry to GeoJSON. '
          'Use getInfo() instead.')

    return self.encode()

  def toGeoJSONString(self):
    """Returns a GeoJSON string representation of the geometry."""
    if self.func:
      raise ee_exception.EEException(
          'Can\'t convert a computed geometry to GeoJSON. '
          'Use getInfo() instead.')
    return json.dumps(self.toGeoJSON())

  def serialize(self):
    """Returns the serialized representation of this object."""
    return serializer.toJSON(self)

  def __str__(self):
    return 'ee.Geometry(%s)' % serializer.toReadableJSON(self)

  @staticmethod
  def _isValidGeometry(geometry):
    """Check if a geometry looks valid.

    Args:
      geometry: The geometry to check.

    Returns:
      True if the geometry looks valid.
    """
    if not isinstance(geometry, dict):
      return False
    geometry_type = geometry.get('type')
    if geometry_type == 'GeometryCollection':
      geometries = geometry.get('geometries')
      if not isinstance(geometries, (list, tuple)):
        return False
      for sub_geometry in geometries:
        if not Geometry._isValidGeometry(sub_geometry):
          return False
      return True
    else:
      coords = geometry.get('coordinates')
      nesting = Geometry._isValidCoordinates(coords)
      return ((geometry_type == 'Point' and nesting == 1) or
              (geometry_type == 'MultiPoint' and
               (nesting == 2 or not coords)) or
              (geometry_type == 'LineString' and nesting == 2) or
              (geometry_type == 'LinearRing' and nesting == 2) or
              (geometry_type == 'MultiLineString' and
               (nesting == 3 or not coords)) or
              (geometry_type == 'Polygon' and nesting == 3) or
              (geometry_type == 'MultiPolygon' and
               (nesting == 4 or not coords)))

  @staticmethod
  def _isValidCoordinates(shape):
    """Validate the coordinates of a geometry.

    Args:
      shape: The coordinates to validate.

    Returns:
      The number of nested arrays or -1 on error.
    """
    if not isinstance(shape, collections.Iterable):
      return -1

    if shape and isinstance(shape[0], collections.Iterable):
      count = Geometry._isValidCoordinates(shape[0])
      # If more than 1 ring or polygon, they should have the same nesting.
      for i in xrange(1, len(shape)):
        if Geometry._isValidCoordinates(shape[i]) != count:
          return -1
      return count + 1
    else:
      # Make sure the pts are all numbers.
      for i in shape:
        if not isinstance(i, numbers.Number):
          return -1

      # Test that we have an even number of pts.
      if len(shape) % 2 == 0:
        return 1
      else:
        return -1

  @staticmethod
  def _coordinatesToLine(coordinates):
    """Create a line from a list of points.

    Args:
      coordinates: The points to convert.  Must be list of numbers of
          even length, in the format [x1, y1, x2, y2, ...]

    Returns:
      An array of pairs of points.
    """
    if not (coordinates and isinstance(coordinates[0], numbers.Number)):
      return coordinates
    if len(coordinates) == 2:
      return coordinates
    if len(coordinates) % 2 != 0:
      raise ee_exception.EEException('Invalid number of coordinates: %s' %
                                     len(coordinates))

    line = []
    for i in xrange(0, len(coordinates), 2):
      pt = [coordinates[i], coordinates[i + 1]]
      line.append(pt)
    return line

  @staticmethod
  def _parseArgs(ctor_name, depth, args):
    """Parses arguments into a GeoJSON dictionary or a ComputedObject.

    Args:
      ctor_name: The name of the constructor to use.
      depth: The nesting depth at which points are found.
      args: The array of values to test.

    Returns:
      If the arguments are simple, a GeoJSON object describing the geometry.
      Otherwise a ComputedObject calling the appropriate constructor.
    """
    result = {}
    keys = ['coordinates', 'crs', 'geodesic', 'maxError']

    if all(ee_types.isNumber(i) for i in args):
      # All numbers, so convert them to a true array.
      result['coordinates'] = args
    else:
      # Parse parameters by position.
      if len(args) > len(keys):
        raise ee_exception.EEException(
            'Geometry constructor given extra arguments.')
      for key, arg in zip(keys, args):
        if arg is not None:
          result[key] = arg

    # Standardize the coordinates and test if they are simple enough for
    # client-side initialization.
    if (Geometry._hasServerValue(result['coordinates']) or
        result.get('crs') is not None or
        result.get('geodesic') is not None or
        result.get('maxError') is not None):
      # Some arguments cannot be handled in the client, so make a server call.
      server_name = 'GeometryConstructors.' + ctor_name
      return apifunction.ApiFunction.lookup(server_name).apply(result)
    else:
      # Everything can be handled here, so check the depth and init this object.
      result['type'] = ctor_name
      result['coordinates'] = Geometry._fixDepth(depth, result['coordinates'])
      return result

  @staticmethod
  def _hasServerValue(coordinates):
    """Returns whether any of the coordinates are computed values or geometries.

    Computed items must be resolved by the server (evaluated in the case of
    computed values, and processed to a single projection and geodesic state
    in the case of geometries.

    Args:
      coordinates: A nested list of ... of number coordinates.

    Returns:
      Whether all coordinates are lists or numbers.
    """
    if isinstance(coordinates, (list, tuple)):
      return any(Geometry._hasServerValue(i) for i in coordinates)
    else:
      return isinstance(coordinates, computedobject.ComputedObject)

  @staticmethod
  def _fixDepth(depth, coords):
    """Fixes the depth of the given coordinates.

    Checks that each element has the expected depth as all other elements
    at that depth.

    Args:
      depth: The desired depth.
      coords: The coordinates to fix.

    Returns:
      The fixed coordinates, with the deepest elements at the requested depth.

    Raises:
      EEException: if the depth is invalid and could not be fixed.
    """
    if depth < 1 or depth > 4:
      raise ee_exception.EEException('Unexpected nesting level.')

    # Handle a list of numbers.
    if all(isinstance(i, numbers.Number) for i in coords):
      coords = Geometry._coordinatesToLine(coords)

    # Make sure the number of nesting levels is correct.
    item = coords
    count = 0
    while isinstance(item, (list, tuple)):
      item = item[0] if item else None
      count += 1
    while count < depth:
      coords = [coords]
      count += 1

    if Geometry._isValidCoordinates(coords) != depth:
      raise ee_exception.EEException('Invalid geometry.')

    # Empty arrays should not be wrapped.
    item = coords
    while isinstance(item, (list, tuple)) and len(item) == 1:
      item = item[0]
    if isinstance(item, (list, tuple)) and not item:
      return []

    return coords

  @staticmethod
  def _GetSpecifiedArgs(args, keywords=(), **kwargs):
    """Returns args, filtering out _UNSPECIFIED and checking for keywords."""
    if keywords:
      args = list(args)
      for i, keyword in enumerate(keywords):
        if keyword in kwargs:
          assert args[i] is _UNSPECIFIED
          args[i] = kwargs[keyword]
    return [i for i in args if i != _UNSPECIFIED]

  @staticmethod
  def name():
    return 'Geometry'
