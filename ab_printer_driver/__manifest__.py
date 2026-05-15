{
    'name': 'Printer Driver',
    'version': '18.0.1.0.0',
    'category': 'Tools',
    'summary': 'Base printer driver — detect, verify, dispatch, log. '
               'Domain-agnostic. POS / accounting / sales / stock consumers '
               'depend on this for thermal + network printing.',
    'description': """
Printer Driver (base)
=====================

Pure hardware-driver layer:

* Model ``ab.printer.config`` — registry of physical printers
  (network / IoT / USB / Bluetooth / agent)
* Model ``ab.printer.category`` — operator-defined groups
* Model ``ab.printer.log``     — every print attempt audited
* Model ``ab.printer.job``     — queue with retry + bus notifications
* Per-(ip, port) ``threading.Lock`` serialises two callers on the same
  thermal printer (single TCP client hardware limit)
* ESC/POS builders + JPEG/PNG → GS v 0 raster helper
* OWL Network Scanner client action — discover, verify, register
* JSON HTTP API ``/ab_printer/scan/*`` and ``/ab_printer/dispatch``

Consumers (POS, accounting, sales, stock) layer thin modules on top.
No business-domain dependencies.
    """,
    'author': 'Sala Integrated Solutions / Ghaima Tech',
    'website': 'https://ghaima.sa',
    'license': 'LGPL-3',
    'depends': ['base', 'web', 'bus', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/printer_category_data.xml',
        'data/ir_cron_data.xml',
        'wizard/printer_detect_wizard_views.xml',
        'views/printer_config_views.xml',
        'views/printer_log_views.xml',
        'views/printer_job_views.xml',
        'views/printer_menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'ab_printer_driver/static/src/css/printer_scan.scss',
            'ab_printer_driver/static/src/css/printer_scanner.scss',
            'ab_printer_driver/static/src/css/live_monitor.scss',
            'ab_printer_driver/static/src/js/printer_scanner/printer_scanner.js',
            'ab_printer_driver/static/src/js/printer_scanner/printer_scanner.xml',
            'ab_printer_driver/static/src/js/live_monitor/live_monitor.js',
            'ab_printer_driver/static/src/js/live_monitor/live_monitor.xml',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
