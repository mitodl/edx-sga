/* Javascript for StaffGradedAssignmentXBlock. */
function StaffGradedAssignmentXBlock(runtime, element) {
    function xblock($, _) {
        var uploadUrl = runtime.handlerUrl(element, 'upload_assignment');
        var finalizeUploadUrl = runtime.handlerUrl(element, 'finalize_uploaded_assignment');
        var downloadUrl = runtime.handlerUrl(element, 'download_assignment');
        var annotatedUrl = runtime.handlerUrl(element, 'download_annotated');
        var getStaffGradingUrl = runtime.handlerUrl(
          element, 'get_staff_grading_data'
        );
        var staffDownloadUrl = runtime.handlerUrl(element, 'staff_download');
        var staffAnnotatedUrl = runtime.handlerUrl(
          element, 'staff_download_annotated'
        );
        var staffUploadUrl = runtime.handlerUrl(element, 'staff_upload_annotated');
        var enterGradeUrl = runtime.handlerUrl(element, 'enter_grade');
        var removeGradeUrl = runtime.handlerUrl(element, 'remove_grade');
        var downloadSubmissionsUrl = runtime.handlerUrl(element, 'download_submissions');
        var prepareDownloadSubmissionsUrl = runtime.handlerUrl(element, 'prepare_download_submissions');
        var downloadSubmissionsStatusUrl = runtime.handlerUrl(element, 'download_submissions_status');
        var template = _.template($(element).find("#sga-tmpl").text());
        var gradingTemplate;
        var preparingSubmissionsMsg = gettext(
          'Started preparing student submissions zip file. This may take a while.'
        );

        function render(state) {
            // Add download urls to template context
            state.downloadUrl = downloadUrl;
            state.annotatedUrl = annotatedUrl;
            state.error = state.error || false;

            // Render template
            var content = $(element).find('#sga-content').html(template(state));

            $(content).find('.finalize-upload').on('click', function() {
              $.post(finalizeUploadUrl).success(
                  function (state) {
                      render(state);
                  }
              ).fail(
                  function () {
                      state.error = gettext('Submission failed. Please contact your course instructor.');
                      render(state);
                  }
              );
            });

            // Set up file upload
            var fileUpload = $(content).find('.fileupload').fileupload({
                url: uploadUrl,
                add: function(e, data) {
                    var do_upload = $(content).find('.upload').html('');
                    $(content).find('p.error').html('');
                    do_upload.text(gettext('Uploading...'));
                    var block = $(element).find(".sga-block");
                    var data_max_size = block.attr("data-max-size");
                    var size = data.files[0].size;
                    if (!_.isUndefined(size)) {
                        //if file size is larger max file size define in env(django)
                        if (size >= data_max_size) {
                            state.error = gettext('The file you are trying to upload is too large.');
                            render(state);
                            return;
                        }
                    }
                    data.submit();
                },
                progressall: function(e, data) {
                    var percent = parseInt(data.loaded / data.total * 100, 10);
                    $(content).find('.upload').text(
                        'Uploading... ' + percent + '%');
                },
                fail: function(e, data) {
                    /**
                     * Nginx and other sanely implemented servers return a
                     * "413 Request entity too large" status code if an
                     * upload exceeds its limit.  See the 'done' handler for
                     * the not sane way that Django handles the same thing.
                     */
                    if (data.jqXHR.status === 413) {
                        /* I guess we have no way of knowing what the limit is
                         * here, so no good way to inform the user of what the
                         * limit is.
                         */
                        state.error = gettext('The file you are trying to upload is too large.');
                    } else {
                        // Suitably vague
                        state.error = gettext('There was an error uploading your file.');

                        // Dump some information to the console to help someone
                        // debug.
                        console.log('There was an error with file upload.');
                        console.log('event: ', e);
                        console.log('data: ', data);
                    }
                    render(state);
                },
                done: function(e, data) {
                    /* When you try to upload a file that exceeds Django's size
                     * limit for file uploads, Django helpfully returns a 200 OK
                     * response with a JSON payload of the form:
                     *
                     *   {'success': '<error message'}
                     *
                     * Thanks Obama!
                     */
                    if (data.result.success !== undefined) {
                        // Actually, this is an error
                        state.error = data.result.success;
                        render(state);
                    } else {
                        // The happy path, no errors
                        render(data.result);
                    }
                }
            });

            updateChangeEvent(fileUpload);
        }

        function renderStaffGrading(data) {
            if (data.hasOwnProperty('error')) {
              gradeFormError(data['error']);
            } else {
              gradeFormError('');
              $('.grade-modal').hide();
            }

            if (data.display_name !== '') {
                $('.sga-block .display_name').html(data.display_name);
            }

            // Add download urls to template context
            data.downloadUrl = staffDownloadUrl;
            data.annotatedUrl = staffAnnotatedUrl;

            // Render template
            $(element).find('#grade-info')
                .html(gradingTemplate(data))
                .data(data);

            // Map data to table rows
            data.assignments.map(function(assignment) {
              $(element).find('#grade-info #row-' + assignment.module_id).data(assignment);
            });

            // Set up grade entry modal
            $(element).find('.enter-grade-button')
                .leanModal({closeButton: '#enter-grade-cancel'})
                .on('click', handleGradeEntry);

            // Set up annotated file upload
            $(element).find('#grade-info .fileupload').each(function() {
                var row = $(this).parents("tr");
                var url = staffUploadUrl + "?module_id=" + row.data("module_id");
                var fileUpload = $(this).fileupload({
                    url: url,
                    progressall: function(e, data) {
                        var percent = parseInt(data.loaded / data.total * 100, 10);
                        row.find('.upload').text(interpolate(gettext('Uploading... %(percent)s %'), {percent: percent}, true));
                    },
                    done: function(e, data) {
                        // Add a time delay so user will notice upload finishing
                        // for small files
                        setTimeout(
                            function() { renderStaffGrading(data.result); },
                            3000);
                    }
                });

                updateChangeEvent(fileUpload);
            });
            $.tablesorter.addParser({
              id: 'alphanum',
              is: function(s) {
                return false;
              },
              format: function(s) {
                var str = s.replace(/(\d{1,2})/g, function(a){
                    return pad(a);
                });

                return str;
              },
              type: 'text'
            });

            $.tablesorter.addParser({
                id: 'yesno',
                is: function(s) {
                    return false;
                },
                format: function(s) {
                    return s.toLowerCase().trim() === gettext('yes') ? 1 : 0;
                },
                type: 'text'
            });

            function pad(num) {
              var s = '00000' + num;
              return s.substr(s.length-5);
            }
            $("#submissions").tablesorter({
                headers: {
                  2: { sorter: "alphanum" },
                  3: { sorter: "alphanum" },
                  4: { sorter: "yesno" },
                  7: { sorter: "alphanum" }
                }
            });
            $("#submissions").trigger("update");
            var sorting = [[4,1], [1,0]];
            $("#submissions").trigger("sorton",[sorting]);
        }

        function isStaff() {
          return $(element).find('.sga-block').attr('data-staff') === 'True';
        }

        /* Just show error on enter grade dialog */
        function gradeFormError(error) {
            var form = $(element).find("#enter-grade-form");
            form.find('.error').html(error);
        }

        /* Click event handler for "enter grade" */
        function handleGradeEntry() {
            var row = $(this).parents("tr");
            var form = $(element).find("#enter-grade-form");
            $(element).find('#student-name').text(row.data('fullname'));
            form.find('#module_id-input').val(row.data('module_id'));
            form.find('#submission_id-input').val(row.data('submission_id'));
            form.find('#grade-input').val(row.data('score'));
            form.find('#comment-input').text(row.data('comment'));
            form.off('submit').on('submit', function(event) {
                var max_score = row.parents('#grade-info').data('max_score');
                var score = Number(form.find('#grade-input').val());
                event.preventDefault();
                if (!score) {
                    gradeFormError('<br/>'+gettext('Grade must be a number.'));
                } else if (score !== parseInt(score)) {
                    gradeFormError('<br/>'+gettext('Grade must be an integer.'));
                } else if (score < 0) {
                    gradeFormError('<br/>'+gettext('Grade must be positive.'));
                } else if (score > max_score) {
                    gradeFormError('<br/>'+interpolate(gettext('Maximum score is %(max_score)s'), {max_score:max_score}, true));
                } else {
                    // No errors
                    $.post(enterGradeUrl, form.serialize())
                        .success(renderStaffGrading);
                }
            });
            form.find('#remove-grade').on('click', function(event) {
                var url = removeGradeUrl + '?module_id=' +
                    row.data('module_id') + '&student_id=' +
                    row.data('student_id');
                event.preventDefault();
                if (row.data('score')) {
                  // if there is no grade then it is pointless to call api.
                  $.get(url).success(renderStaffGrading);
                } else {
                    gradeFormError('<br/>'+gettext('No grade to remove.'));
                }
            });
            form.find('#enter-grade-cancel').on('click', function() {
                /* We're kind of stretching the limits of leanModal, here,
                 * by nesting modals one on top of the other.  One side effect
                 * is that when the enter grade modal is closed, it hides
                 * the overlay for itself and for the staff grading modal,
                 * so the overlay is no longer present to click on to close
                 * the staff grading modal.  Since leanModal uses a fade out
                 * time of 200ms to hide the overlay, our work around is to
                 * wait 225ms and then just "click" the 'Grade Submissions'
                 * button again.  It would also probably be pretty
                 * straightforward to submit a patch to leanModal so that it
                 * would work properly with nested modals.
                 *
                 * See: https://github.com/mitodl/edx-sga/issues/13
                 */
                setTimeout(function() {
                    $('#grade-submissions-button').click();
                    gradeFormError('');
                }, 225);
            });
        }

        function updateChangeEvent(fileUploadObj) {
            fileUploadObj.off('change').on('change', function (e) {
                var that = $(this).data('blueimpFileupload'),
                    data = {
                        fileInput: $(e.target),
                        form: $(e.target.form)
                    };

                that._getFileInputFiles(data.fileInput).always(function (files) {
                    data.files = files;
                    if (that.options.replaceFileInput) {
                        that._replaceFileInput(data.fileInput);
                    }
                    that._onAdd(e, data);
                });
            });
        }

        $(function($) { // onLoad
            var block = $(element).find('.sga-block');
            var state = block.attr('data-state');
            var parsedState = JSON.parse(state);
            render(parsedState);

            var is_staff = isStaff();
            if (is_staff) {
                gradingTemplate = _.template(
                    $(element).find('#sga-grading-tmpl').text());
                block.find('#grade-submissions-button')
                    .leanModal()
                    .on('click', function() {
                        $.ajax({
                            url: getStaffGradingUrl,
                            success: renderStaffGrading
                        });
                    });
                block.find('#staff-debug-info-button')
                    .leanModal();

                $(element).find('#download-init-button').click(function(e) {
                  e.preventDefault();
                  var self = this;
                  $.get(prepareDownloadSubmissionsUrl).then(
                    function(data) {
                      if (data["downloadable"]) {
                        window.location = downloadSubmissionsUrl;
                        $(self).removeClass("disabled");
                      } else {
                        $(self).addClass("disabled");
                        $(element).find('.task-message')
                          .show()
                          .html(preparingSubmissionsMsg)
                          .removeClass("ready-msg")
                          .addClass("preparing-msg");
                        pollSubmissionDownload();
                      }
                    }
                  ).fail(
                    function() {
                      $(self).removeClass("disabled");
                      $(element).find('.task-message')
                        .show()
                        .html(
                          interpolate(
                            gettext(
                              'The download file was not created. Please try again or contact %(support_email)s'
                            ),
                            {support_email: $(element).find('.sga-block').attr("data-support-email")},
                            true
                          )
                        )
                        .removeClass("preparing-msg")
                        .addClass("ready-msg");
                    }
                  );
                });
            }
        });

        function pollSubmissionDownload() {
          pollUntilSuccess(downloadSubmissionsStatusUrl, checkResponse, 10000, 100).then(function() {
            $(element).find('#download-init-button').removeClass("disabled");
            $(element).find('.task-message')
              .show()
              .html(gettext("Student submission file ready for download"))
              .removeClass("preparing-msg")
              .addClass("ready-msg");
          }).fail(function() {
            $(element).find('#download-init-button').removeClass("disabled");
            $(element).find('.task-message')
              .show()
              .html(
                interpolate(
                  gettext(
                    'The download file was not created. Please try again or contact %(support_email)s'
                  ),
                  {support_email: $(element).find('.sga-block').attr("data-support-email")},
                  true
                )
              );
          });
        }
    }

    function checkResponse(response) {
      return response["zip_available"];
    }

    function pollUntilSuccess(url, checkSuccessFn, intervalMs, maxTries) {
      var deferred = $.Deferred(),
        tries = 1;

      function makeLoopingRequest() {
        $.get(url).success(function(response) {
          if (checkSuccessFn(response)) {
            deferred.resolve(response);
          } else if (tries < maxTries) {
            tries++;
            setTimeout(makeLoopingRequest, intervalMs);
          } else {
            deferred.reject('Max tries exceeded.');
          }
        }).fail(function(err) {
          deferred.reject('Request failed:\n' + err.responseText);
        });
      }
      makeLoopingRequest();

      return deferred.promise();
    }

    function loadjs(url) {
        $('<script>')
            .attr('type', 'text/javascript')
            .attr('src', url)
            .appendTo(element);
    }

    if (require === undefined) {
        /**
         * The LMS does not use require.js (although it loads it...) and
         * does not already load jquery.fileupload.  (It looks like it uses
         * jquery.ajaxfileupload instead.  But our XBlock uses
         * jquery.fileupload.
         */
        loadjs('/static/js/vendor/jQuery-File-Upload/js/jquery.iframe-transport.js');
        loadjs('/static/js/vendor/jQuery-File-Upload/js/jquery.fileupload.js');
        xblock($, _);
    } else {
        /**
         * Studio, on the other hand, uses require.js and already knows about
         * jquery.fileupload.
         */
        require(['jquery', 'underscore', 'jquery.fileupload'], xblock);
    }
}
