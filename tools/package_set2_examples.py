"""Losslessly package the user-authorized Set2 CZI scans for the static demo."""
import argparse, hashlib, json
from pathlib import Path
import czifile
import numpy as np
import tifffile

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('source_directory', type=Path)
args = parser.parse_args()
for key, filename in [('jk-set2-base','Base-1_x20x2.czi'),('jk-set2-mid','Mid-1_x20x2.czi')]:
    path = root/'starter'/f'{key}.json'
    metadata = json.loads(path.read_text())
    source = args.source_directory/filename
    original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if original_hash != metadata['original_sha256']:
        raise ValueError(f'Unexpected source checksum for {filename}')
    with czifile.CziFile(source) as czi:
        array, axes = czi.asarray(), czi.axes
    for i in reversed(range(len(axes))):
        if axes[i] not in 'ZCYX':
            if array.shape[i] != 1:
                raise ValueError(f'Unsupported non-singleton axis {axes[i]}')
            array = np.take(array,0,axis=i)
            axes = axes[:i]+axes[i+1:]
    array = array.transpose([axes.index(a) for a in 'ZCYX'])
    assert list(array.shape) == metadata['shape']
    target = root/'starter'/f'{key}.ome.tif'
    sx,sy,sz = metadata['spacing']
    tifffile.imwrite(target,array,ome=True,photometric='minisblack',compression='deflate',metadata={
        'axes':'ZCYX','PhysicalSizeX':sx,'PhysicalSizeY':sy,'PhysicalSizeZ':sz,
        'PhysicalSizeXUnit':'µm','PhysicalSizeYUnit':'µm','PhysicalSizeZUnit':'µm',
        'Channel':{'Name':metadata['channels']}})
    np.testing.assert_array_equal(tifffile.imread(target),array)
    metadata.update(path=f'starter/{target.name}',local_only=False,
        sha256_packaged=hashlib.sha256(target.read_bytes()).hexdigest(),
        pixel_transform='Identity: all channels, full XY, all acquired Z planes; lossless OME-TIFF container conversion only')
    path.write_text(json.dumps(metadata,indent=2)+'\n')
    print(key, array.shape, target.stat().st_size, 'bytes; exact pixel equality verified')
