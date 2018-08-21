/*
 * Custom behavior for the lightsheet landing page
*/
var dataIo = dataIo || {};

/*
 * Grab data and submit it when pressing the button
 */
dataIo.customSubmit = function(){

  console.log(lightsheet.currentTemplate);
  debugger;
  const url = window.origin;
  const formInput = $('form :input');
  // Initialize object which will contain data to be posted
  var data = {}

  const jobField = $('#jobId');
  let job_name = null;
  if (jobField && jobField.length > 0) {
    data['jobName'] = $('#jobId')[0].value;
  }

  //Get the checkboxes for steps, which are checked
  const checked_boxes = $('form :input[id^=check-]:checked');
  
  // Store values of multi-select checkboxes in corresponding input fields
  var innerFieldClass = 'filter-option-inner-inner';
  var multiCheckboxClass = 'custom-multi-checkbox';
  var checkBoxInnerFields = document.getElementsByClassName(multiCheckboxClass);

  for (var i = 0; i < checkBoxInnerFields.length; i++) {
    var selectedElements = checkBoxInnerFields[i].getElementsByClassName(innerFieldClass)[0].innerHTML;
    var outputField = checkBoxInnerFields[i].getElementsByTagName('input')[0];

    var result = "[" + selectedElements + "]";
    if (selectedElements == "Nothing selected") {
      outputField = []
    }
    else {
      outputField.value = result;
    }
  }

  // Submit empty values
  checked_boxes.each( function( index, element ){
    const step = this.id.replace('check-','');
      data[step] = {};
      var inputFields = $('#collapse' + step).find('input');
      inputFields.each( function(k,val) {
        if (this.disabled) {
          data[step][val.id] = "[]";
        }
        else {
          if (val.value) {
            data[step][val.id] = val.value;  
          }
          else {

          }
        }
      })
  });

  var finalUrl = url + "/" + location.search;
  console.log(data);
  const formDataRequest = new Request(finalUrl, { method: 'POST' });
  fetch(url + "/" + location.search, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(data)
  }).then(function(response) {
      return response.json();
  }).then(function(data) {
    console.log('error in fetch');
  });
}