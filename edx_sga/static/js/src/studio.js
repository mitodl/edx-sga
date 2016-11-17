function StaffGradedAssignmentXBlock(runtime, element, server) {
    var saveUrl = runtime.handlerUrl(element, 'save_sga');

    var validators = {
        'number': function(x) {
            return Number(x);
        },
        'string': function(x) {
            return !x ? null : x;
        }
    };

    function save() {
        var view = this;
        view.runtime.notify('save', {state: 'start'});

        var data = {};
        $(element).find('input').each(function(index, input) {
            data[input.name] = input.value;
        });

        $.ajax({
            type: 'POST',
            url: saveUrl,
            data: JSON.stringify(data),
            success: function() {
                view.runtime.notify('save', {state: 'end'});
            }
        });
    }

    return {
        save: save
    };
}
