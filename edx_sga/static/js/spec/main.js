(function(requirejs, define) {
    requirejs.config({
        paths: {
            'jquery': 'lib/jquery-2.1.4',
            'sinon': 'js/lib/sinon-1.16.1',
            'URI': 'js/lib/URI',
            'underscore': 'js/lib/underscore'
        },
        shim: {
            'underscore': {
                exports: "_"
            },
            'sinon': {
                exports: "sinon"
            },
            'URI': {
                exports: 'URI',
                deps: ['sinon']
            }
        }
    });

    define("main", [
        'js/spec/test_studio'
    ]);
    
})(requirejs, define);
