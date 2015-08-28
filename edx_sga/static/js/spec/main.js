(function(requirejs, define) {
    requirejs.config({
        paths: {
            'jquery': 'js/bower/jquery/dist/jquery',
            'sinon': 'js/bower/sinon/lib/sinon',
            'URI': 'js/bower/URIjs/src/URI',
            'underscore': 'js/bower/underscore/underscore',
            'IPv6': 'js/bower/URIjs/src/IPv6',
            'punycode': 'js/bower/URIjs/src/punycode',
            'SecondLevelDomains': 'js/bower/URIjs/src/SecondLevelDomains'
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
