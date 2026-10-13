"""Single stable entry point for launchers; never auto-executes game input."""
import argparse
import runpy
import sys
from app.project_paths import ensure_runtime_dirs

COMMANDS={
    'map':'app.map_editor.gui',
    'route':'app.navigation.route_runner',
    'single-point':'app.navigation.single_point_test',
    'turning-probe':'app.navigation.turning_probe',
    'heading-step':'app.navigation.heading_step_probe',
    'scan-sequence':'app.navigation.scan_sequence',
    'temporal-step':'app.navigation.temporal_step_probe',
    'record':'app.navigation.coordinate_recorder',
    'ocr-region':'app.navigation.region_selector',
    'minimap-region':'app.navigation.minimap_region_selector',
    'download-maps':'tools.maps.download_offline_tiles',
    'verify-maps':'tools.maps.verify_offline_tiles',
}

def main():
    parser=argparse.ArgumentParser(description='鸣潮项目统一入口')
    parser.add_argument('command',choices=COMMANDS)
    args,remaining=parser.parse_known_args()
    ensure_runtime_dirs()
    sys.argv=[COMMANDS[args.command],*remaining]
    runpy.run_module(COMMANDS[args.command],run_name='__main__')

if __name__=='__main__':main()
