describe("studio.js", function() {
    'use strict';
    describe("StaffGradedAssignmentXBlock", function() {
        beforeEach(function() {
            jasmine.Ajax.install();
        });

        afterEach(function() {
            jasmine.Ajax.uninstall();
        });

        it("saves the view", function() {
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

            // Mock a response to the POST
            jasmine.Ajax.stubRequest(
                fakeUrl, JSON.stringify({
                    one: "1",
                    two: "2",
                    three: "3"
                }), "POST"
            ).andReturn({responseText: "{}"});

            // Execute the save
            XBlock.save();

            var request = jasmine.Ajax.requests.mostRecent();
            expect(request.status).toBe(200);
            expect(request.url).toBe(fakeUrl);
            expect(notifyStates.save.state).toBe('end');
        });

    });
});
