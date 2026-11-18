"""Exercise the published weather init across a real asynchronous location swap."""
import io
import json
from pathlib import Path
import subprocess
import zipfile

import pytest

from lyra.candidate_compat import validate_weather_location_patch
from lyra.mod_archive import source_mod_zip_bytes


SOURCE = Path(__file__).resolve().parents[1] / "mods/dolx-compat"


def test_source_archive_includes_weather_patch_and_game_license(tmp_path):
    payload = source_mod_zip_bytes(SOURCE)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        assert archive.read("patches/weather-location.json") == (SOURCE / "patches/weather-location.json").read_bytes()
        assert archive.read("LICENSE-WEATHER.txt") == (SOURCE / "LICENSE-WEATHER.txt").read_bytes()
    path = tmp_path / "compat.zip"
    path.write_bytes(payload)
    entry, = json.loads((SOURCE / "patches/weather-location.json").read_text(encoding="utf-8"))["js"]
    validate_weather_location_patch(entry["from"], path)
    with pytest.raises(RuntimeError, match="expected one weather init, got 0"):
        validate_weather_location_patch(entry["to"], path)
    with pytest.raises(RuntimeError, match="expected one weather init, got 2"):
        validate_weather_location_patch(entry["from"] * 2, path)


def test_weather_location_owns_pending_images_and_preserves_missing_asset_errors(tmp_path):
    fixture = r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const patch = JSON.parse(fs.readFileSync(process.argv[2], 'utf8')).js[0];
function setup(source) {
  const requested=[], errors=[], animations=[];
  let resolveFirst;
  const first=new Promise(resolve=>{resolveFirst=resolve;});
  const context={Map,Promise,window:{ImageCache:{getOrCreate:path=>{
    requested.push(path);
    return path==='img/misc/locations/bloodmoon/first.png'?first:
      path.endsWith('/missing.png')?Promise.reject(new Error('missing resource')):
      Promise.resolve({src:path,width:128,height:256});
  }}},Errors:{report:message=>errors.push(message)},resolveValue:(value,fallback)=>value??fallback,
  Weather:{Renderer:{Animation:class {constructor(options){this.options=options;animations.push(options);}enable(){}}}}};
  vm.createContext(context);
  vm.runInContext(`String.prototype.deepCopy=function(){return this.toString();};
    Object.prototype.deepCopy=function(){return Object.fromEntries(Object.entries(this).map(([k,v])=>
    [k,v&&typeof v==='object'?Object.assign({},v):v]));};`,context);
  const receiver=vm.runInContext(`({key:'base',fullPath:'img/misc/locations/bloodmoon/',
    location:{base:{bloodmoonTentacles1:{image:'first.png'},bloodmoonTentacles4:{image:'tentacles4.png'}}},
    canvas:{element:{width:128,height:256}},parentLayer:{animationGroup:{add(){}}}})`,context);
  const home=vm.runInContext(`({base:{default:{image:'base.png'},snow:{image:'snow.png'}}})`,context);
  const init=vm.runInContext('({'+source+'}).init',context);
  return {receiver,home,init,requested,errors,resolveFirst,context,animations};
}
async function swap(source) {
  const t=setup(source);
  const pending=t.init.call(t.receiver);
  t.receiver.location=t.home;t.receiver.fullPath='img/misc/locations/home/';
  await t.init.call(t.receiver);
  t.resolveFirst({src:'img/misc/locations/bloodmoon/first.png',width:128,height:256});
  await pending;
  return t;
}
(async()=>{
  const original=await swap(patch.from);
  assert.ok(original.requested.includes('img/misc/locations/home/[object Object]'),
    'The actual published init must reproduce the old-loop/new-object failure');
  const fixed=await swap(patch.to);
  assert.deepEqual(fixed.requested,['img/misc/locations/bloodmoon/first.png',
    'img/misc/locations/home/base.png','img/misc/locations/home/snow.png']);
  assert.deepEqual([...fixed.receiver.animations.keys()],['default','snow']);
  assert.equal(fixed.receiver.animations.get('default').image.src,'img/misc/locations/home/base.png');
  assert.equal(fixed.receiver.animations.get('snow').image.src,'img/misc/locations/home/snow.png');
  assert.equal(fixed.errors.length,0);
  const direct=setup(patch.to);direct.receiver.location=vm.runInContext('({base:"direct.png"})',direct.context);
  direct.receiver.fullPath='img/misc/locations/forest/';await direct.init.call(direct.receiver);
  assert.deepEqual(direct.requested,['img/misc/locations/forest/direct.png']);
  const missing=setup(patch.to);missing.receiver.location=vm.runInContext('({base:{image:"missing.png"}})',missing.context);
  missing.receiver.fullPath='img/misc/locations/home/';await missing.init.call(missing.receiver);
  assert.deepEqual(missing.requested,['img/misc/locations/home/missing.png']);
  assert.deepEqual(missing.errors,['Warning: Missing location image: img/misc/locations/home/missing.png']);
  assert.equal(missing.receiver.animations.size,0);
  const animation=setup(patch.to);animation.receiver.location=vm.runInContext('({base:{image:"animated.png",animation:{frameDelay:2}}})',animation.context);
  animation.receiver.fullPath='img/misc/locations/home/';await animation.init.call(animation.receiver);
  assert.equal(animation.animations.length,1);assert.equal(animation.animations[0].frameDelay,2);
  assert.equal(animation.animations[0].image.src,'img/misc/locations/home/animated.png');
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
    path = tmp_path / "weather-regression.js"
    path.write_text(fixture, encoding="utf-8")
    result = subprocess.run(["node", str(path), str(SOURCE / "patches/weather-location.json")],
                            capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
