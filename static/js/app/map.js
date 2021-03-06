/**
 Daniel Simpson,
 John Wilshire

 2017

 Functions related to the Map, adding layers, adding markers
*/

function addLayerControl (layerNum, label, classification) {
  var slider = document.createElement('div')
  noUiSlider.create(slider, {
    start: 100,
    connect: [true, false],
    range: {
      'min': 0,
      'max': 100
    },
    step: 1,
    format: wNumb({ decimals: 0 })
  })
  slider.noUiSlider.on('update', function (values, handle) {
    map.overlayMapTypes.getAt(layerNum - 1).setOpacity(parseInt(values[0]) / 100)
  })
  var selector = classification ? '#classification-control' : '#predictor-control'
  $(selector).empty().append(
    $('<label>').text(label).append(
    $('<div>').attr('class', '.no-ui-slider').append(slider)
  ))
}

/**
  Gets the predictor layer from the server.
  If reset is true we will ask the server to re-calculate visualization parameters.
*/
function predictorVis (reset) {
  var select = $('#predictorVis')
  var val = select.val()
  var postData = {
    predictor: val,
    region: regionPath(),
    sigma: Number($('#sigma').val())
  }
  if (!reset) {
    postData.mean = vis.mean
    postData.total_sd = vis.total_sd
  }
  if(val === 'natural' || val === 'past-natural'){
    if(!$('#sigma-div').hasClass('hidden')){
      $('#sigma-div').addClass('hidden')
    }
  } else if($('#sigma-div').hasClass('hidden')){
    $('#sigma-div').removeClass('hidden')
  }
  // set the select to disabled while we send the request for the vis layer
  select.prop('disabled', true)
  select.material_select()
  $('#spinner').show()
  $.post(
    '/getpredictorlayer',
    JSON.stringify(postData),
    function (data) {
      $('#spinner').hide()
      var eeMapOptions = {
        getTileUrl: buildGetTileUrl(data.mapid, data.token),
        tileSize: new google.maps.Size(256, 256)
      }
      // Create the map type.
      var mapType = new google.maps.ImageMapType(eeMapOptions)
      if (map.overlayMapTypes.length === 0) {
        map.overlayMapTypes.push(mapType)
      } else {
        map.overlayMapTypes.setAt(0, mapType)
      }
      addLayerControl(1, 'Predictor: ' +  $('#predictorVis option:selected').text(), false)
      var layers = localStorage.getItem('layers')
      if (layers != null) {
        addClassifiedMap(JSON.parse(layers))
        localStorage.removeItem('layers')
      }
      vis.mean = data.mean
      vis.total_sd = data.total_sd
    }, 'json').fail(
    function (err) {
      console.log(err)
      Materialize.toast('Failed to get predictor layer.', 10000, 'rounded')
    }).always(function () { 
      // re-enable the predictor selector
      $('#sigma').material_select()
      select.prop('disabled', false)
      select.material_select()
    })
}

/** Higher order function that allows for google maps to request for tiles of a map type.
*/
function buildGetTileUrl (mapid, token) {
  return function (tile, zoom) {
    var baseUrl = 'https://earthengine.googleapis.com/map'
    return [baseUrl, mapid, zoom, tile.x, tile.y].join('/') + '?token=' + token
  }
}

/*
* Allows a user to add markers of a class by clicking on the map.
*/
function addMarkers () {
  if (listenerHandle === false) {
    $('#map div .gm-style div').css('cursor', 'crosshair')
    $('#addMarkers').addClass('active')
    region.setEditable(false)
    listenerHandle = google.maps.event.addListener(map, 'click', function (event) {
      if (google.maps.geometry.poly.containsLocation(event.latLng, region)) {
        // add the event marker
        var idx = parseInt($('.classVal.active').attr('id'))
        var badge = $('li#' + idx + ' a .badge')
        badge.text(parseInt(badge.text()) + 1)
        var marker = new google.maps.Marker({
          position: event.latLng,
          map: map,
          draggable: true,
          icon: getIcon(classList[idx].colour)
        })
        classList[idx].markers.push(marker)
      } else {
        Materialize.toast('Please focus region before training a classification.', 2000, 'rounded')
      }
    })
    $('.button-collapse').sideNav('hide')
  } else {
    $('#map div .gm-style div').css('cursor', '')
    $('#addMarkers').removeClass('active')
    region.setEditable(true)
    google.maps.event.removeListener(listenerHandle)
    listenerHandle = false
  }
}

// toggles the markers visibility on the map
function markerVisibility () {
  var button = $('#marker-toggle')
  var toggle = button.attr('data') === '1'
  classList.forEach(function(x) {
    x.markers.forEach(function(y) {
      y.setVisible(toggle)
    })
  })
  button.attr('data', toggle ? '0' : '1')
}

function addClassifiedMap (data) {
  $('#spinner').hide()
  localStorage.setItem('layers', JSON.stringify(data))
  data.forEach(function (layer, i) {
    var eeMapOptions = {
      getTileUrl: buildGetTileUrl(layer.mapid, layer.token),
      tileSize: new google.maps.Size(256, 256)
    }
    // Create the map type.
    layer.label = (past ? "1999-2003":"2014-2017") + ": " + layer.label
    var mapType = new google.maps.ImageMapType(eeMapOptions)
    if (!classified) {
      classified = true
      map.overlayMapTypes.push(mapType)
      addLayerControl(map.overlayMapTypes.length, layer.label, true)
    } else {
      map.overlayMapTypes.pop()
      map.overlayMapTypes.push(mapType)
      addLayerControl(map.overlayMapTypes.length, layer.label, true)
    }
  })
  $('#classify').text('4. Reclassify!')
}

function getIcon(colour) {
  return {
      path: google.maps.SymbolPath.BACKWARD_CLOSED_ARROW,
      fillColor: colour,
      fillOpacity: 0.6,
      strokeColor: 'white',
      strokeWeight: 0.5,
      scale: 4
    }
}

function getMapJSON () {
  return JSON.stringify({
    'classes': getClasses(),
    'region': getRegion()
  })
}

function loginClick () {
  window.onbeforeunload = null; // turn off the confirmation for the login redirect
  localStorage.setItem('mapData', getMapJSON())
}
