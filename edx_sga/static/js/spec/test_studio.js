define(["js/spec_helpers/ajax_helpers", "js/src/studio"], function(AjaxHelpers) {
    'use strict';
    describe("studio.js", function() {
        describe("StaffGradedAssignmentXBlock", function() {
            it("saves the view", function() {
                // Spy on Ajax requests
                var requests = AjaxHelpers.requests(this);
                
                // Mock some arguments
                var fakeUrl = "/test_url/";
                var element = $("<div>" +
                                "<input type='hidden' name='one' value='1' />" +
                                "<input type='hidden' name='two' value='2' />" +
                                "<input type='hidden' name='three' value='3' /></div>");
                var server = null;

                var runtime = {
                    handlerUrl: function() {
                        return fakeUrl;
                    },
                    notify: function(type, state) {
                        notifyStates[type] = state;
                    }
                };

                var XBlock = StaffGradedAssignmentXBlock(runtime, element, server);
                // Function expects this.runtime to exist
                XBlock.save = XBlock.save.bind({runtime: runtime});

                var notifyStates = {};

                // Execute the save
                XBlock.save();

                // Verify the request was made
                AjaxHelpers.expectRequest(
                    requests, 'POST', fakeUrl, JSON.stringify({
                        one: "1",
                        two: "2",
                        three: "3"
                    })
                );

                // Complete ajax request
                AjaxHelpers.respondWithJson(requests, {});
                
                expect(notifyStates.save.state).toBe('end');
            });

        });
    });
});
