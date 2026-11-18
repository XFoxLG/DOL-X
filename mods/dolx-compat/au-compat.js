/*
 * DOL-X AU face and pet compatibility, maintained by XFoxLG.
 * AU layer behavior: AOKIUTAGE's AU face expansion 1.2.16.
 * Framework API: MaplebirchLeaf, MapleBirch 5.6.2.
 * Attribution and distribution terms are recorded in README.md.
 */
;(() => {
  if (!modUtils.getModListName().includes('AU面部扩展')) return;
  if (window.dolxCompat) throw new Error('DOL-X 兼容包重复初始化');
  for (const [name, version] of [['maplebirch', '5.6.2'], ['AU面部扩展', '1.2.16']]) {
    const mod = modUtils.getMod(name);
    if (mod.version !== version) {
      throw new Error('DOL-X 兼容包不支持 ' + name + '@' + mod.version);
    }
  }
  window.dolxCompat = {
    version: '1.0.1', phase: 'normal-script',
    beforeCaches: Object.keys(Renderer.CanvasModelCaches.main || {}),
    registered: false, registrationCount: 0, petCaptureCount: 0
  };
  // Exact inventory from the reviewed 0.5.12.13 candidate base face assets.
  // BSA's active model assets always take precedence over this base inventory.
  const dolxBaseFacePaths = new Set([
    "img/face/default/aloof/brow-low.png",
    "img/face/default/aloof/brow-mid.png",
    "img/face/default/aloof/brow-orgasm.png",
    "img/face/default/aloof/brow-top.png",
    "img/face/default/aloof/eyelids-half-closed.png",
    "img/face/default/aloof/eyelids.png",
    "img/face/default/aloof/eyes.png",
    "img/face/default/aloof/iris-empty-half-closed.png",
    "img/face/default/aloof/iris-empty.png",
    "img/face/default/aloof/iris-half-closed.png",
    "img/face/default/aloof/iris.png",
    "img/face/default/aloof/lashes-half-closed.png",
    "img/face/default/aloof/lashes.png",
    "img/face/default/aloof/makeup/eyeshadow-half-closed.png",
    "img/face/default/aloof/makeup/eyeshadow.png",
    "img/face/default/aloof/makeup/mascara-half-closed.png",
    "img/face/default/aloof/makeup/mascara.png",
    "img/face/default/aloof/makeup/mascara1.png",
    "img/face/default/aloof/makeup/mascara2.png",
    "img/face/default/aloof/makeup/mascara3.png",
    "img/face/default/aloof/makeup/mascara4.png",
    "img/face/default/aloof/sclera-bloodshot.png",
    "img/face/default/aloof/sclera.png",
    "img/face/default/blush-1.png",
    "img/face/default/blush-2.png",
    "img/face/default/blush-3.png",
    "img/face/default/blush-4.png",
    "img/face/default/blush-5.png",
    "img/face/default/blusher.png",
    "img/face/default/catty/brow-low.png",
    "img/face/default/catty/brow-mid.png",
    "img/face/default/catty/brow-orgasm.png",
    "img/face/default/catty/brow-top.png",
    "img/face/default/catty/eyelids-half-closed.png",
    "img/face/default/catty/eyelids.png",
    "img/face/default/catty/eyes.png",
    "img/face/default/catty/iris-empty-half-closed.png",
    "img/face/default/catty/iris-empty.png",
    "img/face/default/catty/iris-half-closed.png",
    "img/face/default/catty/iris.png",
    "img/face/default/catty/lashes-half-closed.png",
    "img/face/default/catty/lashes.png",
    "img/face/default/catty/makeup/eyeshadow-half-closed.png",
    "img/face/default/catty/makeup/eyeshadow.png",
    "img/face/default/catty/makeup/mascara-half-closed.png",
    "img/face/default/catty/makeup/mascara.png",
    "img/face/default/catty/makeup/mascara1.png",
    "img/face/default/catty/makeup/mascara2.png",
    "img/face/default/catty/makeup/mascara3.png",
    "img/face/default/catty/makeup/mascara4.png",
    "img/face/default/catty/sclera-bloodshot.png",
    "img/face/default/catty/sclera.png",
    "img/face/default/default/blush-1.png",
    "img/face/default/default/blush-2.png",
    "img/face/default/default/blush-3.png",
    "img/face/default/default/blush-4.png",
    "img/face/default/default/blush-5.png",
    "img/face/default/default/blusher.png",
    "img/face/default/default/brow-low.png",
    "img/face/default/default/brow-mid.png",
    "img/face/default/default/brow-orgasm.png",
    "img/face/default/default/brow-top.png",
    "img/face/default/default/eyelids-half-closed.png",
    "img/face/default/default/eyelids.png",
    "img/face/default/default/eyes.png",
    "img/face/default/default/iris-empty-half-closed.png",
    "img/face/default/default/iris-empty.png",
    "img/face/default/default/iris-half-closed.png",
    "img/face/default/default/iris.png",
    "img/face/default/default/lashes-half-closed.png",
    "img/face/default/default/lashes.png",
    "img/face/default/default/makeup/eyeshadow-half-closed.png",
    "img/face/default/default/makeup/eyeshadow.png",
    "img/face/default/default/makeup/mascara-half-closed.png",
    "img/face/default/default/makeup/mascara.png",
    "img/face/default/default/makeup/mascara1.png",
    "img/face/default/default/makeup/mascara2.png",
    "img/face/default/default/makeup/mascara3.png",
    "img/face/default/default/makeup/mascara4.png",
    "img/face/default/default/mouth-chew.png",
    "img/face/default/default/mouth-cry.png",
    "img/face/default/default/mouth-frown.png",
    "img/face/default/default/mouth-neutral.png",
    "img/face/default/default/mouth-smile.png",
    "img/face/default/default/sclera-bloodshot.png",
    "img/face/default/default/sclera.png",
    "img/face/default/ears.png",
    "img/face/default/foxy/brow-low.png",
    "img/face/default/foxy/brow-mid.png",
    "img/face/default/foxy/brow-orgasm.png",
    "img/face/default/foxy/brow-top.png",
    "img/face/default/foxy/eyelids-half-closed.png",
    "img/face/default/foxy/eyelids.png",
    "img/face/default/foxy/eyes.png",
    "img/face/default/foxy/iris-empty-half-closed.png",
    "img/face/default/foxy/iris-empty.png",
    "img/face/default/foxy/iris-half-closed.png",
    "img/face/default/foxy/iris.png",
    "img/face/default/foxy/lashes-half-closed.png",
    "img/face/default/foxy/lashes.png",
    "img/face/default/foxy/makeup/eyeshadow-half-closed.png",
    "img/face/default/foxy/makeup/eyeshadow.png",
    "img/face/default/foxy/makeup/mascara-half-closed.png",
    "img/face/default/foxy/makeup/mascara.png",
    "img/face/default/foxy/makeup/mascara1.png",
    "img/face/default/foxy/makeup/mascara2.png",
    "img/face/default/foxy/makeup/mascara3.png",
    "img/face/default/foxy/makeup/mascara4.png",
    "img/face/default/foxy/sclera-bloodshot.png",
    "img/face/default/foxy/sclera.png",
    "img/face/default/freckles.png",
    "img/face/default/gloomy/brow-low.png",
    "img/face/default/gloomy/brow-mid.png",
    "img/face/default/gloomy/brow-orgasm.png",
    "img/face/default/gloomy/brow-top.png",
    "img/face/default/gloomy/eyelids-half-closed.png",
    "img/face/default/gloomy/eyelids.png",
    "img/face/default/gloomy/eyes.png",
    "img/face/default/gloomy/iris-empty-half-closed.png",
    "img/face/default/gloomy/iris-empty.png",
    "img/face/default/gloomy/iris-half-closed.png",
    "img/face/default/gloomy/iris.png",
    "img/face/default/gloomy/lashes-half-closed.png",
    "img/face/default/gloomy/lashes.png",
    "img/face/default/gloomy/makeup/eyeshadow-half-closed.png",
    "img/face/default/gloomy/makeup/eyeshadow.png",
    "img/face/default/gloomy/makeup/mascara-half-closed.png",
    "img/face/default/gloomy/makeup/mascara.png",
    "img/face/default/gloomy/makeup/mascara1.png",
    "img/face/default/gloomy/makeup/mascara2.png",
    "img/face/default/gloomy/makeup/mascara3.png",
    "img/face/default/gloomy/makeup/mascara4.png",
    "img/face/default/gloomy/sclera-bloodshot.png",
    "img/face/default/gloomy/sclera.png",
    "img/face/default/lipstick-chew.png",
    "img/face/default/lipstick-cry.png",
    "img/face/default/lipstick-frown.png",
    "img/face/default/lipstick-neutral.png",
    "img/face/default/lipstick-smile.png",
    "img/face/default/mouth-chew.png",
    "img/face/default/mouth-cry.png",
    "img/face/default/mouth-frown.png",
    "img/face/default/mouth-neutral.png",
    "img/face/default/mouth-smile.png",
    "img/face/default/sweet/brow-low.png",
    "img/face/default/sweet/brow-mid.png",
    "img/face/default/sweet/brow-orgasm.png",
    "img/face/default/sweet/brow-top.png",
    "img/face/default/sweet/eyelids-half-closed.png",
    "img/face/default/sweet/eyelids.png",
    "img/face/default/sweet/eyes.png",
    "img/face/default/sweet/iris-empty-half-closed.png",
    "img/face/default/sweet/iris-empty.png",
    "img/face/default/sweet/iris-half-closed.png",
    "img/face/default/sweet/iris.png",
    "img/face/default/sweet/lashes-half-closed.png",
    "img/face/default/sweet/lashes.png",
    "img/face/default/sweet/makeup/eyeshadow-half-closed.png",
    "img/face/default/sweet/makeup/eyeshadow.png",
    "img/face/default/sweet/makeup/mascara-half-closed.png",
    "img/face/default/sweet/makeup/mascara.png",
    "img/face/default/sweet/makeup/mascara1.png",
    "img/face/default/sweet/makeup/mascara2.png",
    "img/face/default/sweet/makeup/mascara3.png",
    "img/face/default/sweet/makeup/mascara4.png",
    "img/face/default/sweet/sclera-bloodshot.png",
    "img/face/default/sweet/sclera.png",
    "img/face/default/tears-1.png",
    "img/face/default/tears-2.png",
    "img/face/default/tears-3.png",
    "img/face/default/tears-4.png",
    "img/face/masks/left.png",
    "img/face/masks/right.png"
  ]);
  const faceStyleSrcFn =
      typeof maplebirch.char.faceStyleSrcFn === 'function'
          ? maplebirch.char.faceStyleSrcFn
          : function (name) {
              const getName =
                  typeof name === 'function'
                      ? name
                      : () => name;

              return function (o) {
                  const images = [getName(o)].flat();

                  const facestyle = o.facestyle || 'default';
                  const facevariant = o.facevariant || 'default';

                  const candidates = images.flatMap(image => {
                      return facestyle === 'default' &&
                          /^(freckles|ears|blusher|mouth-|lipstick-|blush-?|tears?-?)/.test(image)
                          ? [
                              `img/face/${facestyle}/${image}.png`,
                              `img/face/${facestyle}/${facevariant}/${image}.png`,
                              `img/face/default/${image}.png`,
                              `img/face/default/${facevariant}/${image}.png`
                          ]
                          : [
                              `img/face/${facestyle}/${facevariant}/${image}.png`,
                              `img/face/${facestyle}/${image}.png`,
                              `img/face/default/${facevariant}/${image}.png`,
                              `img/face/default/${image}.png`
                          ];
                  });

                  for (const path of candidates) {
                      if (addonBeautySelectorAddon.checkImageExist(path)) return path;
                      // Published AU model packs retain the singular tear-N name.
                      const legacyTear = path.replace(/\/tears-(\d+)\.png$/, '/tear-$1.png');
                      if (legacyTear !== path && addonBeautySelectorAddon.checkImageExist(legacyTear)) return legacyTear;
                  }
                  for (const path of candidates) {
                      if (dolxBaseFacePaths.has(path)) return path;
                  }
                  return candidates[0];
              };
          };

  const layers = {
      // ===== 眼睛 =====
      eyes: {
          srcfn: (o) => {
              if (!V.SE.au_eyes_show || !o.show_face) return "";
              const selected = V.SE.mixFaceEnable
                  ? { ...o, facestyle: V.SE.eyesFacestyle, facevariant: V.SE.variant_eyes } : o;
              const path = faceStyleSrcFn('eyes')(selected);
              return addonBeautySelectorAddon.checkImageExist(path) || dolxBaseFacePaths.has(path) ? path : "";
          },
          showfn: (o) =>
              V.SE.au_eyes_show && o.show_face        
      },
      ears: {                 
            srcfn: faceStyleSrcFn('ears', { variant: true })
      },               
      left_iris: {
          srcfn: faceStyleSrcFn(
              (o) => {
                  const orgasm = V.SE.org_exp && V.orgasmdown >= 1 ? "-orgasm" : "";
                  const empty = o.trauma ? "-empty" : "";
                  const half = o.eyes_half ? "-half-closed" : "";
                  return `iris${orgasm}${empty}${half}`;
              },
              { variant: true }
          )
      },
      right_iris: {
          srcfn: faceStyleSrcFn(
              (o) => {
                  const orgasm = V.SE.org_exp && V.orgasmdown >= 1 ? "-orgasm" : "";
                  const empty = o.trauma ? "-empty" : "";
                  const half = o.eyes_half ? "-half-closed" : "";
                  return `iris${orgasm}${empty}${half}`;
              },
              { variant: true }
          )
      },
      freckles: {
          srcfn: faceStyleSrcFn('freckles', { variant: true })
      },

      // ===== 嘴巴相關 =====
      mouth: {
          srcfn: (o) =>
              V.SE?.mixFaceEnable
                  ? `img/face/${V.SE.mouthFacestyle}/${V.SE.variant_mouth}/mouth-${o.mouth}.png`
                  : faceStyleSrcFn((o) => `mouth-${o.mouth}`)(o)
      },
      makeup_lipstick: {
          srcfn: (o) =>
              V.SE?.mixFaceEnable
                  ? `img/face/${V.SE.mouthFacestyle}/${V.SE.variant_mouth}/lipstick-${o.mouth}.png`
                  : faceStyleSrcFn((o) => `lipstick-${o.mouth}`)(o)
      },
      blush: {
          srcfn: (o) =>
              V.SE?.mixFaceEnable
                  ? `img/face/${V.SE.mouthFacestyle}/${V.SE.variant_mouth}/blush-${o.blush}.png`
                  : faceStyleSrcFn((o) => `blush-${o.blush}`)(o)
      },
      makeup_blusher: {
          srcfn: faceStyleSrcFn('blusher', { variant: true })
      },
      tears: {
          srcfn: (o) => o.tears > 0 ? faceStyleSrcFn((o) => `tears-${o.tears}`, { variant: true })(o) : ''
      }
  };

  // ===== 一次性使用 maplebirch.char.use =====
  maplebirch.char.use(layers, "main", { pet: true });
  window.dolxCompat.registrationCount += 1;
  // 5.6.2 captures the pet definition before normal mod scripts run.
  // Re-capture once during initialization with the registered AU layers.
  delete Renderer.CanvasModels.pet;
  maplebirch.char.pet.capture(Renderer.CanvasModels.main);
  window.dolxCompat.petCaptureCount += 1;
  window.dolxCompat.registered = true;
})();
