;(function () {
  "use strict";

  // maplebirch v3.1.14 sidebar/face layer-naming compatibility shim.
  //
  // WHY THIS EXISTS
  //   maplebirch v3.1.14 (the last 3.x release, kept because maplebirchExpansion
  //   v1.2.4 has no 4.x build) generates NPC-sidebar body layers and the PC blush
  //   face layer with the OLD un-hyphenated DoLP naming (basehead.png, breasts0.png,
  //   leftarmidle-classic.png, blush1.png). Game 0.5.9.8+ and the AU art packs both
  //   ship the NEW hyphenated naming (base-head.png, breasts-0.png,
  //   left-arm-idle-classic.png, blush-1.png). The names never line up, so those
  //   layers 404 ("Failed to load image ... for layer nnpc_head/blush").
  //
  //   maplebirch v4.1.6-v4.1.12 fixed this by switching every layer to the hyphenated
  //   names. This mod back-ports exactly those srcfn changes onto 3.x through the
  //   public `maplebirch.char.use()` API — no framework source is patched.
  //
  // HOW IT STAYS SAFE
  //   `char.use(layerMap)` deep-MERGES into the layer registry (see Character.use ->
  //   merge(this.layers, obj)). We only override each layer's `srcfn`; every other
  //   field (showfn/zfn/dxfn/dyfn/filters/animation/masksrcfn) is left untouched and
  //   keeps the framework's own logic. Because this mod depends on maplebirch it loads
  //   AFTER the framework, so our merge lands last and wins for the srcfn leaf.

  function getFramework() {
    return typeof window !== "undefined" ? window.maplebirch : undefined;
  }

  // Mirror v4's nnpc_head fallback: prefer the facestyle head, else the base body head.
  // Uses the framework's own loadImage (exposed via maplebirch.tool.utils) so the
  // existence probe matches the framework's image resolution exactly.
  function resolveHead(mb, facestyle) {
    var path = "img/face/" + facestyle + "/base-head.png";
    try {
      var loadImage = mb && mb.tool && mb.tool.utils && mb.tool.utils.loadImage;
      if (typeof loadImage === "function" && loadImage(path) === false) {
        return "img/body/base-head.png";
      }
    } catch (e) {
      return "img/body/base-head.png";
    }
    return path;
  }

  // Body layers: only the layers whose v3 srcfn used the old naming need overriding.
  // Definitions transcribed from maplebirch v4.1.12 base_layers.ts, adapted to plain JS.
  function buildBodyLayers(mb) {
    return {
      nnpc_head: {
        srcfn: function (options) {
          var nnpc = options.maplebirch.nnpc;
          if (nnpc.model) return resolveHead(mb, nnpc.facestyle);
          // Non-model (clothes-art) path: defer to framework default by returning
          // undefined so the merged framework srcfn value is not shadowed for this case.
          // The framework's own srcfn already handles the art lookup; we only reach here
          // when model===false, which never produced the broken basehead.png request.
          var display = ((V.options.maplebirch || {}).npcsidebar || {}).display || {};
          var selected = display[nnpc.name];
          var art = mb.npc && mb.npc.Clothes && mb.npc.Clothes.layers
            ? mb.npc.Clothes.layers.get(nnpc.name)
            : undefined;
          if (!selected) return undefined;
          if (art && selected === art.key) return art.head && art.head.img;
          return undefined;
        }
      },
      nnpc_body: {
        srcfn: function (options) {
          var nnpc = options.maplebirch.nnpc;
          if (nnpc.model) return "img/body/base-classic.png";
          var display = ((V.options.maplebirch || {}).npcsidebar || {}).display || {};
          var selected = display[nnpc.name];
          var art = mb.npc && mb.npc.Clothes && mb.npc.Clothes.layers
            ? mb.npc.Clothes.layers.get(nnpc.name)
            : undefined;
          if (!selected) return undefined;
          if (art && selected === art.key) return art.body;
          return undefined;
        }
      },
      nnpc_breasts: {
        srcfn: function (options) {
          var nnpc = options.maplebirch.nnpc;
          if (!nnpc.breasts) return "";
          var size = nnpc.breast_size || 0;
          var type = nnpc.breasts === "cleavage" && size >= 3 ? "clothed" : "breasts";
          return "img/body/breasts/" + type + "-" + size + ".png";
        }
      },
      nnpc_leftarm: {
        srcfn: function (options) {
          var nnpc = options.maplebirch.nnpc;
          if (nnpc.arm_left === "cover") return "img/body/left-arm-cover.png";
          return "img/body/left-arm-idle-classic.png";
        }
      },
      nnpc_rightarm: {
        srcfn: function (options) {
          var nnpc = options.maplebirch.nnpc;
          if (nnpc.arm_right === "idle" || !nnpc.arm_right) {
            return "img/body/right-arm-idle-classic.png";
          }
          return "img/body/right-arm-" + nnpc.arm_right + ".png";
        }
      }
    };
  }

  // Face layer: blush uses hyphenated naming in v4 (blush-N vs v3's blushN).
  // Rebuild it with the framework's own faceStyleSrcFn so the 5-level fallback
  // cascade is identical to the framework — only the leaf name gains its hyphen.
  function buildFaceLayers(mb) {
    var faceStyleSrcFn = mb.char && mb.char.faceStyleSrcFn;
    if (typeof faceStyleSrcFn !== "function") return null;
    return {
      blush: {
        srcfn: faceStyleSrcFn(function (options) {
          return "blush-" + options.blush;
        })
      }
    };
  }

  function applyCompat() {
    var mb = getFramework();
    if (!mb || !mb.char || typeof mb.char.use !== "function") {
      return false;
    }

    var bodyLayers = buildBodyLayers(mb);
    mb.char.use(bodyLayers);

    var faceLayers = buildFaceLayers(mb);
    if (faceLayers) mb.char.use(faceLayers);

    if (typeof mb.log === "function") {
      mb.log(
        "[v3-layer-compat] backported hyphenated nnpc_/blush layer naming onto v3.x",
        "INFO"
      );
    }
    return true;
  }

  function register() {
    var mb = getFramework();
    if (!mb || typeof mb.once !== "function") {
      // Framework not ready yet; retry on the next macro task.
      setTimeout(register, 50);
      return;
    }
    // :storyready fires after the framework's own NPCSidebar.init() has registered
    // the base layers, so our override merges last and wins. once() auto-unsubscribes.
    mb.once(":storyready", applyCompat, "v3-layer-compat apply");
  }

  register();
})();
