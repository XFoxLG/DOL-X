;(function () {
  "use strict";

  // maplebirch v3.1.14 sidebar/face layer-naming compatibility shim.
  //
  // WHY THIS EXISTS
  //   maplebirch v3.1.14 (the last 3.x release, kept because maplebirchExpansion
  //   v1.2.4 has no 4.x build) generates NPC-sidebar layers with the OLD
  //   un-hyphenated DoLP naming:
  //     - body/face:  basehead.png, breasts0.png, leftarmidle-classic.png, blush1.png
  //     - clothes:    img/clothes/over_upper/.../acc_full.png (underscore folder + suffix)
  //   Game 0.5.9.8+ and the AU art packs ship the NEW hyphenated naming:
  //     - body/face:  base-head.png, breasts-0.png, left-arm-idle-classic.png, blush-1.png
  //     - clothes:    img/clothes/over-upper/.../acc-full.png (hyphen folder + suffix)
  //   The names never line up, so those layers 404. Body layers show a broken
  //   silhouette; CLOTHES layers silently vanish -> NPC sidebar renders naked.
  //
  //   maplebirch v4.1.6-v4.1.12 fixed this by (a) running every clothes slot folder
  //   through normaliseFileName() (over_upper -> over-upper) and (b) switching every
  //   filename suffix from _alt/_down/_acc/_rolled to -alt/-down/-acc/-rolled. This
  //   mod back-ports exactly those srcfn changes onto 3.x through the public
  //   `maplebirch.char.use()` API — no framework source is patched.
  //
  // HOW IT STAYS SAFE
  //   `char.use(layerMap)` deep-MERGES into the layer registry (see Character.use ->
  //   merge(this.layers, obj)). We override ONLY each layer's `srcfn`; every other
  //   field (showfn/zfn/dxfn/dyfn/filters/masksrcfn/animation) keeps the framework's
  //   own v3 logic untouched. This is deliberate: the naming bug lives purely in
  //   srcfn (which path to request); visibility (showfn) and z-order (zfn, which
  //   reads maplebirch.char.ZIndices.*) are correct in v3 already, so leaving them
  //   alone avoids any dependence on v3-vs-v4 ZIndices key differences.
  //
  //   v4's gray_suffix() is a no-op (returns the path unchanged), so the srcfn port
  //   needs no colour-filter state at all — the path is a pure function of nnpc.clothes.
  //   Because this mod depends on maplebirch it loads AFTER the framework, and applies
  //   on :storyready (after NPCSidebar.init registered the base layers), so our merge
  //   lands last and wins for the srcfn leaf.
  //
  // DELIBERATELY NOT PORTED
  //   - nnpc_penis: v3 renames it (penis{n}.png / penis_chastity.png) while the game
  //     ships hard-{n}/soft-{n}/chastity.png under penis/ + penis-no-balls/. BUT v3's
  //     srcfn opens with `if (!!nnpc.name) return ''`, so this layer never renders for
  //     the NAMED sidebar NPCs this addon draws; and v4 reads a different data model
  //     (nnpc.balls + a full penis descriptor) that v3's NPCSidebar never populates.
  //     A char.use() override can't reconstruct v4's inputs from v3 state, so porting
  //     it would only trade one wrong path for another. Left as v3's own no-op.
  //   - Face leaves (eyes/iris/sclera/lashes/eyelids/brows/mouth/ears/freckles): v3 and
  //     v4 build byte-identical face paths, so there is no naming bug to fix. Any
  //     missing-eyes.png style errors are an AU face-mod resource issue, not this bug.
  //   - Sidepart wrappers (upper/lower/legs/feet/hands): return a pre-stored art .img,
  //     never a constructed body path, so they have no naming bug either.

  function getFramework() {
    return typeof window !== "undefined" ? window.maplebirch : undefined;
  }

  // ---- shared helpers (transcribed from maplebirch v4.1.12 functions.ts) --------

  // v4 normaliseFileName: strip accents, split camelCase, collapse whitespace/-/_
  // into a single hyphen, lowercase. Applied to the clothes SLOT (folder segment)
  // only — never to the garment `variable`, which legitimately contains underscores
  // (e.g. thighhigh_heels, fur_boots, pumpkin_dress).
  function normaliseFileName(text) {
    return String(text)
      .normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/([A-Z])/g, "-$1")
      .replace(/[\s\-_]+/g, "-")
      .toLowerCase();
  }

  function inc(arr, val) {
    return !!arr && arr.indexOf(val) !== -1;
  }

  function dash(pattern) {
    return pattern ? String(pattern).replace(/ /g, "-") : "";
  }

  var PROP_CATEGORIES = [
    "food", "ingredient", "recipe", "tending", "antique",
    "sex toy", "child toy", "book", "furniture"
  ];

  function propCategory(handheld) {
    if (!inc(handheld.type, "prop")) return "";
    var found = null;
    for (var i = 0; i < handheld.type.length; i++) {
      if (PROP_CATEGORIES.indexOf(handheld.type[i]) !== -1) {
        found = handheld.type[i];
        break;
      }
    }
    return (found || "general") + "/";
  }

  function armState(nnpc, side) {
    var arm = nnpc["arm_" + side];
    if (arm === "cover") return "cover";
    if (side === "right" && nnpc.handheld_position === "hold") return "hold";
    if (side === "right" && nnpc.handheld_position === "right_cover") return "cover";
    return arm === "idle" ? "idle" : arm;
  }

  function handSuffix(nnpc, side) {
    var arm = nnpc["arm_" + side];
    if (side === "left") return arm === "cover" ? "left-cover" : "left";
    if (arm === "cover") return "right-cover";
    if (nnpc.handheld_position === "hold") return "right-hold";
    if (nnpc.handheld_position === "right_cover") return "right-cover";
    return "right";
  }

  // ---- srcfn builders (return a plain srcfn; path is a pure function of state) ---

  function clothesLayerSrc(slot, type) {
    return function (options) {
      var nnpc = options.maplebirch.nnpc;
      var clothes = nnpc.clothes[slot];
      var folder = normaliseFileName(slot);
      if (type === "detail") {
        var altd = clothes.altposition === "alt" ? "-alt" : "";
        return "img/clothes/" + folder + "/" + clothes.variable + "/" + dash(clothes.pattern) + altd + ".png";
      }
      var down = (nnpc.hood_down || clothes.hoodposition === "down") &&
        clothes.hoodposition != null && clothes.outfitPrimary && clothes.outfitPrimary.head != null;
      var alt = clothes.altposition === "alt" &&
        (type === "main" ? !inc(clothes.altdisabled, "full")
          : type === "acc" ? !inc(clothes.altdisabled, "acc") : false);
      var pattern = "", prefix = "", suffix = "";
      if (type === "main") {
        pattern = clothes.pattern && ["secondary", "tertiary"].indexOf(clothes.pattern_layer) === -1 ? "-" + dash(clothes.pattern) : "";
        prefix = clothes.integrity;
        suffix = down ? "-down" : alt ? "-alt" : "";
      } else if (type === "acc") {
        pattern = clothes.pattern && clothes.pattern_layer === "secondary" ? "-" + dash(clothes.pattern) : "";
        prefix = "acc" + (clothes.accessory_integrity_img ? "-" + clothes.integrity : "");
        suffix = down ? "-down" : alt ? "-alt" : "";
      }
      return "img/clothes/" + folder + "/" + clothes.variable + "/" + prefix + pattern + suffix + ".png";
    };
  }

  function clothesBreastsSrc(slot, type) {
    return function (options) {
      var nnpc = options.maplebirch.nnpc;
      var clothes = nnpc.clothes[slot];
      var folder = normaliseFileName(slot);
      var breastSize;
      if (type === "acc") {
        breastSize = (typeof clothes.breast_acc_img === "object") ? clothes.breast_acc_img[nnpc.breast_size]
          : (typeof clothes.breast_img === "object") ? clothes.breast_img[nnpc.breast_size]
            : Math.min(nnpc.breast_size, 6);
      } else {
        breastSize = (typeof clothes.breast_img === "object") ? clothes.breast_img[nnpc.breast_size] : Math.min(nnpc.breast_size, 6);
      }
      if (type === "detail") {
        var pd = clothes.pattern ? "-" + dash(clothes.pattern) : "";
        return "img/clothes/" + folder + "/" + clothes.variable + "/" + breastSize + pd + ".png";
      }
      var alt = clothes.altposition === "alt" && type === "main" && !inc(clothes.altdisabled, "breasts");
      var pattern = "", extension = "";
      if (type === "main") {
        pattern = clothes.pattern && ["tertiary", "secondary"].indexOf(clothes.pattern_layer) === -1 ? "-" + dash(clothes.pattern) : "";
      } else if (type === "acc") {
        pattern = clothes.pattern && clothes.pattern_layer === "secondary" ? "-" + dash(clothes.pattern) : "";
        extension = "-acc";
      }
      return "img/clothes/" + folder + "/" + clothes.variable + "/" + breastSize + extension + pattern + (alt ? "-alt" : "") + ".png";
    };
  }

  function clothesArmSrc(slot, side) {
    return function (options) {
      var nnpc = options.maplebirch.nnpc;
      var clothes = nnpc.clothes[slot];
      var folder = normaliseFileName(slot);
      var altPosition = clothes.altposition === "alt" && !inc(clothes.altdisabled, "sleeves");
      var altSleeve = nnpc.alt_sleeve_state && clothes.altsleeve === "alt";
      var alt = altPosition ? "-alt" : "";
      var rolled = altSleeve ? "-rolled" : "";
      var pattern = clothes.sleeve_colour === "pattern" && clothes.pattern ? "-" + dash(clothes.pattern) : "";
      return "img/clothes/" + folder + "/" + clothes.variable + "/" + side + "-" + armState(nnpc, side) + alt + pattern + rolled + ".png";
    };
  }

  function clothesArmAccSrc(slot, side) {
    return function (options) {
      var nnpc = options.maplebirch.nnpc;
      var clothes = nnpc.clothes[slot];
      var folder = normaliseFileName(slot);
      var altPosition = clothes.altposition === "alt" && !inc(clothes.altdisabled, "sleeves") && !inc(clothes.altdisabled, "sleeve_acc");
      var suffix = altPosition ? "-alt-acc" : "-acc";
      return "img/clothes/" + folder + "/" + clothes.variable + "/" + side + "-" + armState(nnpc, side) + suffix + ".png";
    };
  }

  function clothesBackSrc(slot) {
    return function (options) {
      var nnpc = options.maplebirch.nnpc;
      var clothes = nnpc.clothes[slot];
      var folder = normaliseFileName(slot);
      var altPosition = clothes.altposition === "alt" && !inc(clothes.altdisabled, "back");
      var prefix = altPosition ? "back-alt" : "back";
      var suffix = clothes.back_integrity_img ? "-" + clothes.integrity : "";
      var pattern = clothes.pattern && ["tertiary", "secondary"].indexOf(clothes.pattern_layer) === -1 ? "-" + dash(clothes.pattern) : "";
      return "img/clothes/" + folder + "/" + clothes.variable + "/" + prefix + suffix + pattern + ".png";
    };
  }

  function clothesBackAccSrc(slot) {
    return function (options) {
      var nnpc = options.maplebirch.nnpc;
      var clothes = nnpc.clothes[slot];
      var folder = normaliseFileName(slot);
      var altPosition = clothes.altposition === "alt" && !inc(clothes.altdisabled, "back");
      var prefix = altPosition ? "back-alt" : "back";
      var suffix = clothes.back_integrity_img ? "-" + clothes.integrity : "";
      var pattern = clothes.pattern && clothes.pattern_layer === "secondary" ? "-" + dash(clothes.pattern) : "";
      return "img/clothes/" + folder + "/" + clothes.variable + "/" + prefix + suffix + pattern + "-acc.png";
    };
  }

  function clothesHandSrc(side, type) {
    return function (options) {
      var nnpc = options.maplebirch.nnpc;
      var hands = nnpc.clothes.hands;
      var suffix = handSuffix(nnpc, side);
      var folder = normaliseFileName("hands");
      if (type === "detail") {
        var pd = hands.pattern ? "-" + dash(hands.pattern) : "";
        return "img/clothes/" + folder + "/" + hands.variable + "/" + suffix + pd + ".png";
      }
      var pattern = "", extension = "";
      if (type === "main") {
        pattern = hands.pattern && ["tertiary", "secondary"].indexOf(hands.pattern_layer) === -1 ? "-" + dash(hands.pattern) : "";
      } else if (type === "acc") {
        pattern = hands.pattern && hands.pattern_layer === "secondary" ? "-" + dash(hands.pattern) : "";
        extension = "-acc";
      }
      return "img/clothes/" + folder + "/" + hands.variable + "/" + suffix + pattern + extension + ".png";
    };
  }

  function clothesHandheldSrc(type) {
    return function (options) {
      var nnpc = options.maplebirch.nnpc;
      var handheld = nnpc.clothes.handheld;
      var directory = inc(handheld.type, "prop") ? "props" : "handheld";
      var category = propCategory(handheld);
      var cover = nnpc.arm_right === "cover" && nnpc.handheld_position !== "right_cover" ? "right-cover" : "right";
      if (type === "detail") {
        var pd = handheld.pattern ? "-" + dash(handheld.pattern) : "";
        return "img/clothes/" + directory + "/" + category + handheld.variable + "/" + cover + pd + ".png";
      }
      var pattern = "", extension = "";
      if (type === "main") {
        pattern = handheld.pattern && ["tertiary", "secondary"].indexOf(handheld.pattern_layer) === -1 ? "-" + dash(handheld.pattern) : "";
      } else if (type === "acc") {
        pattern = handheld.pattern && handheld.pattern_layer === "secondary" ? "-" + dash(handheld.pattern) : "";
        extension = "-acc";
      }
      return "img/clothes/" + directory + "/" + category + handheld.variable + "/" + cover + pattern + extension + ".png";
    };
  }

  // ---- custom srcfns (layers whose v4 srcfn differs from the generic builders) ---

  function lowerAccSrc(options) {
    var nnpc = options.maplebirch.nnpc;
    var lower = nnpc.clothes.lower;
    var folder = normaliseFileName("lower");
    var secondary = nnpc.clothes.upper.name === "school blouse" && lower.name.indexOf("pinafore") !== -1 ? "-under" : "";
    var integrity = lower.accessory_integrity_img ? "-" + lower.integrity : secondary;
    var pattern = lower.pattern && lower.pattern_layer === "secondary" ? "-" + dash(lower.pattern) : "";
    return "img/clothes/" + folder + "/" + lower.variable + "/acc" + integrity + pattern + ".png";
  }

  function slotPenisSrc(slot) {
    return function (options) {
      var clothes = options.maplebirch.nnpc.clothes[slot];
      return "img/clothes/" + normaliseFileName(slot) + "/" + clothes.variable + "/penis.png";
    };
  }

  function slotPenisAccSrc(slot) {
    return function (options) {
      var clothes = options.maplebirch.nnpc.clothes[slot];
      return "img/clothes/" + normaliseFileName(slot) + "/" + clothes.variable + "/acc-penis.png";
    };
  }

  function neckMainSrc(options) {
    var nnpc = options.maplebirch.nnpc;
    var neck = nnpc.clothes.neck;
    var upper = nnpc.clothes.upper;
    var collar = neck.has_collar === 1 && upper.has_collar === 1 ? "-nocollar"
      : (neck.name === "sailor ribbon" && upper.name === "serafuku" ? "-serafuku" : "");
    var pattern = neck.pattern && ["tertiary", "secondary"].indexOf(neck.pattern_layer) === -1 ? "-" + dash(neck.pattern) : "";
    return "img/clothes/neck/" + neck.variable + "/" + neck.integrity + collar + pattern + ".png";
  }

  function neckAccSrc(options) {
    var neck = options.maplebirch.nnpc.clothes.neck;
    var integrity = neck.accessory_integrity_img ? "-" + neck.integrity : "";
    var pattern = neck.pattern && neck.pattern_layer === "secondary" ? "-" + dash(neck.pattern) : "";
    return "img/clothes/neck/" + neck.variable + "/acc" + integrity + pattern + ".png";
  }

  function headMainSrc(options) {
    var nnpc = options.maplebirch.nnpc;
    var head = nnpc.clothes.head;
    var integrity = head.accessory_integrity_img ? nnpc.clothes.upper.integrity : head.integrity;
    var pattern = head.pattern && ["tertiary", "secondary"].indexOf(head.pattern_layer) === -1 ? "-" + dash(head.pattern) : "";
    return "img/clothes/head/" + head.variable + "/" + integrity + pattern + ".png";
  }

  function headAccSrc(options) {
    var nnpc = options.maplebirch.nnpc;
    var head = nnpc.clothes.head;
    var integrity = head.accessory_integrity_img ? "-" + nnpc.clothes.upper.integrity : "";
    var pattern = head.pattern && head.pattern_layer === "secondary" ? "-" + dash(head.pattern) : "";
    return "img/clothes/head/" + head.variable + "/acc" + integrity + pattern + ".png";
  }

  function headDetailSrc(options) {
    var head = options.maplebirch.nnpc.clothes.head;
    return "img/clothes/head/" + head.variable + "/" + dash(head.pattern) + ".png";
  }

  function handheldSideSrc(acc) {
    return function (options) {
      var nnpc = options.maplebirch.nnpc;
      var handheld = nnpc.clothes.handheld;
      var cover = nnpc.arm_left === "cover" ? "left-cover" : "left";
      var directory = inc(handheld.type, "prop") ? "props" : "handheld";
      var category = propCategory(handheld);
      return "img/clothes/" + directory + "/" + category + handheld.variable + "/" + cover + (acc ? "-acc" : "") + ".png";
    };
  }

  // ---- layer map assembly -------------------------------------------------------

  // Every clothes layer key exactly matches maplebirch v3.1.14's registered keys
  // (verified against v3 *_layers.ts). Value is { srcfn } only — merged onto the
  // framework layer so showfn/zfn/masksrcfn/filters stay as v3's own.
  function buildClothingLayers() {
    var m = {};

    // upper family
    m.nnpc_over_upper_main = { srcfn: clothesLayerSrc("over_upper", "main") };
    m.nnpc_over_upper_acc = { srcfn: clothesLayerSrc("over_upper", "acc") };
    m.nnpc_over_upper_detail = { srcfn: clothesLayerSrc("over_upper", "detail") };
    m.nnpc_over_upper_breasts = { srcfn: clothesBreastsSrc("over_upper", "main") };
    m.nnpc_over_upper_leftarm = { srcfn: clothesArmSrc("over_upper", "left") };
    m.nnpc_over_upper_rightarm = { srcfn: clothesArmSrc("over_upper", "right") };

    m.nnpc_upper_main = { srcfn: clothesLayerSrc("upper", "main") };
    m.nnpc_upper_acc = { srcfn: clothesLayerSrc("upper", "acc") };
    m.nnpc_upper_detail = { srcfn: clothesLayerSrc("upper", "detail") };
    m.nnpc_upper_breasts = { srcfn: clothesBreastsSrc("upper", "main") };
    m.nnpc_upper_breasts_acc = { srcfn: clothesBreastsSrc("upper", "acc") };
    m.nnpc_upper_breasts_detail = { srcfn: clothesBreastsSrc("upper", "detail") };
    m.nnpc_upper_leftarm = { srcfn: clothesArmSrc("upper", "left") };
    m.nnpc_upper_rightarm = { srcfn: clothesArmSrc("upper", "right") };
    m.nnpc_upper_leftarm_acc = { srcfn: clothesArmAccSrc("upper", "left") };
    m.nnpc_upper_rightarm_acc = { srcfn: clothesArmAccSrc("upper", "right") };
    m.nnpc_upper_back = { srcfn: clothesBackSrc("upper") };

    m.nnpc_under_upper_main = { srcfn: clothesLayerSrc("under_upper", "main") };
    m.nnpc_under_upper_acc = { srcfn: clothesLayerSrc("under_upper", "acc") };
    m.nnpc_under_upper_breasts = { srcfn: clothesBreastsSrc("under_upper", "main") };
    m.nnpc_under_upper_breasts_acc = { srcfn: clothesBreastsSrc("under_upper", "acc") };
    m.nnpc_under_upper_breasts_detail = { srcfn: clothesBreastsSrc("under_upper", "detail") };
    m.nnpc_under_upper_leftarm = { srcfn: clothesArmSrc("under_upper", "left") };
    m.nnpc_under_upper_rightarm = { srcfn: clothesArmSrc("under_upper", "right") };
    m.nnpc_under_upper_back = { srcfn: clothesBackSrc("under_upper") };

    // lower family
    m.nnpc_over_lower_main = { srcfn: clothesLayerSrc("over_lower", "main") };
    m.nnpc_over_lower_acc = { srcfn: clothesLayerSrc("over_lower", "acc") };
    m.nnpc_over_lower_detail = { srcfn: clothesLayerSrc("over_lower", "detail") };
    m.nnpc_over_lower_back = { srcfn: clothesBackSrc("over_lower") };

    m.nnpc_lower_main = { srcfn: clothesLayerSrc("lower", "main") };
    m.nnpc_lower_acc = { srcfn: lowerAccSrc };
    m.nnpc_lower_detail = { srcfn: clothesLayerSrc("lower", "detail") };
    m.nnpc_lower_breasts = { srcfn: clothesBreastsSrc("lower", "main") };
    m.nnpc_lower_breasts_acc = { srcfn: clothesBreastsSrc("lower", "acc") };
    m.nnpc_lower_penis = { srcfn: slotPenisSrc("lower") };
    m.nnpc_lower_penis_acc = { srcfn: slotPenisAccSrc("lower") };
    m.nnpc_lower_back = { srcfn: clothesBackSrc("lower") };
    m.nnpc_lower_back_acc = { srcfn: clothesBackAccSrc("lower") };

    m.nnpc_under_lower_main = { srcfn: clothesLayerSrc("under_lower", "main") };
    m.nnpc_under_lower_acc = { srcfn: clothesLayerSrc("under_lower", "acc") };
    m.nnpc_under_lower_detail = { srcfn: clothesLayerSrc("under_lower", "detail") };
    m.nnpc_under_lower_penis = { srcfn: slotPenisSrc("under_lower") };
    m.nnpc_under_lower_penis_acc = { srcfn: slotPenisAccSrc("under_lower") };

    // legs
    m.nnpc_legs_main = { srcfn: clothesLayerSrc("legs", "main") };
    m.nnpc_legs_acc = { srcfn: clothesLayerSrc("legs", "acc") };
    m.nnpc_legs_back = { srcfn: clothesBackSrc("legs") };
    m.nnpc_legs_back_acc = { srcfn: clothesBackAccSrc("legs") };

    // feet
    m.nnpc_feet_main = { srcfn: clothesLayerSrc("feet", "main") };
    m.nnpc_feet_acc = { srcfn: clothesLayerSrc("feet", "acc") };
    m.nnpc_feet_details = { srcfn: clothesLayerSrc("feet", "detail") };
    m.nnpc_feet_back = { srcfn: clothesBackSrc("feet") };
    m.nnpc_feet_back_acc = { srcfn: clothesBackAccSrc("feet") };

    // hands
    m.nnpc_hands_main = { srcfn: clothesLayerSrc("hands", "main") };
    m.nnpc_hands_left = { srcfn: clothesHandSrc("left", "main") };
    m.nnpc_hands_left_acc = { srcfn: clothesHandSrc("left", "acc") };
    m.nnpc_hands_left_detail = { srcfn: clothesHandSrc("left", "detail") };
    m.nnpc_hands_right = { srcfn: clothesHandSrc("right", "main") };
    m.nnpc_hands_right_acc = { srcfn: clothesHandSrc("right", "acc") };
    m.nnpc_hands_right_detail = { srcfn: clothesHandSrc("right", "detail") };

    // neck
    m.nnpc_neck_main = { srcfn: neckMainSrc };
    m.nnpc_neck_acc = { srcfn: neckAccSrc };

    // head family
    m.nnpc_over_head_main = { srcfn: clothesLayerSrc("over_head", "main") };
    m.nnpc_over_head_acc = { srcfn: clothesLayerSrc("over_head", "acc") };
    m.nnpc_over_head_back = { srcfn: clothesBackSrc("over_head") };
    m.nnpc_over_head_back_acc = { srcfn: clothesBackAccSrc("over_head") };
    m.nnpc_head_main = { srcfn: headMainSrc };
    m.nnpc_head_acc = { srcfn: headAccSrc };
    m.nnpc_head_detail = { srcfn: headDetailSrc };
    m.nnpc_head_back = { srcfn: clothesBackSrc("head") };
    m.nnpc_head_back_acc = { srcfn: clothesBackAccSrc("head") };

    // handheld
    m.nnpc_handheld_main = { srcfn: clothesHandheldSrc("main") };
    m.nnpc_handheld_acc = { srcfn: clothesHandheldSrc("acc") };
    m.nnpc_handheld_detail = { srcfn: clothesHandheldSrc("detail") };
    m.nnpc_handheld_left = { srcfn: handheldSideSrc(false) };
    m.nnpc_handheld_left_acc = { srcfn: handheldSideSrc(true) };
    m.nnpc_handheld_back = { srcfn: clothesBackSrc("handheld") };
    m.nnpc_handheld_back_acc = { srcfn: clothesBackAccSrc("handheld") };

    return m;
  }

  // ---- body + face layers (unchanged from the original body-only compat) --------

  // Mirror v4's nnpc_head fallback: prefer the facestyle head, else the base body head.
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

  function buildBodyLayers(mb) {
    return {
      nnpc_head: {
        srcfn: function (options) {
          var nnpc = options.maplebirch.nnpc;
          if (nnpc.model) return resolveHead(mb, nnpc.facestyle);
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

  // ---- apply --------------------------------------------------------------------

  function applyCompat() {
    var mb = getFramework();
    if (!mb || !mb.char || typeof mb.char.use !== "function") {
      return false;
    }

    mb.char.use(buildBodyLayers(mb));
    mb.char.use(buildClothingLayers());

    var faceLayers = buildFaceLayers(mb);
    if (faceLayers) mb.char.use(faceLayers);

    if (typeof mb.log === "function") {
      mb.log(
        "[v3-layer-compat] backported hyphenated nnpc_ body+clothes+blush layer naming onto v3.x",
        "INFO"
      );
    }
    return true;
  }

  function register() {
    var mb = getFramework();
    if (!mb || typeof mb.once !== "function") {
      setTimeout(register, 50);
      return;
    }
    // :storyready fires after the framework's own NPCSidebar.init() has registered
    // the base layers, so our override merges last and wins. once() auto-unsubscribes.
    mb.once(":storyready", applyCompat, "v3-layer-compat apply");
  }

  register();
})();
