"""Project paths shared by applications, tools and tests; independent of cwd."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
MAPS = DATA / 'maps'
ROUTES = DATA / 'routes'
VALIDATION = DATA / 'map_validation'
SAMPLES = VALIDATION / 'samples'
RESEARCH = VALIDATION / 'research'
TREASURE_DATA = DATA / 'treasure'
DATASET = TREASURE_DATA / 'dataset'
INCOMING = TREASURE_DATA / 'incoming'
CONFIG = ROOT / 'config' / 'treasure'
DATASET_CONFIG = CONFIG / 'dataset.yaml'
CLASSES = CONFIG / 'classes.txt'
MODELS = ROOT / 'models' / 'treasure'
DETECTOR_MODEL = MODELS / 'latest.pt'
BASE_MODEL = MODELS / 'base_yolov8n.pt'
TRAINING_RUNS = ROOT / 'outputs' / 'training' / 'treasure'
LOGS = ROOT / 'outputs' / 'logs'
DRAFT_ROUTE = ROUTES / 'gg_route_draft.json'
WAYPOINT_ROUTE = ROUTES / 'waypoints.json'
RECORDED_ROUTE = ROUTES / 'recorded_path.json'
MERGED_RECORD = TREASURE_DATA / 'merged_record.json'
OFFLINE_TILES = MAPS / 'wuthering_gg' / 'tile_cache'


def ensure_runtime_dirs():
    for path in (ROUTES, LOGS, INCOMING, TRAINING_RUNS):
        path.mkdir(parents=True, exist_ok=True)
