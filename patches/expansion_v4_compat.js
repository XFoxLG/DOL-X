// DOL-X TEMPORARY COMPAT PATCH
// Applies to: maplebirchExpansion v1.2.4
// Framework: maplebirch v4.x (tested on v4.1.8)
// Purpose: Polyfill maplebirch.use() which was removed in v4.x
//
// --- END OF LIFE CONDITIONS (remove this patch when any met) ---
// 1. Expansion releases v1.2.5+ with native v4.x support
// 2. Expansion releases any version that supports v4.x natively
// 3. Upstream framework update makes this polyfill incompatible
// ---
//
// Original expansion code calls: maplebirch.use('ExMod')
// In v3.x this pushed 'ExMod' into core array and made it accessible.
// In v4.x use() was removed and ModuleSystem only exposes modules
// with exposed=true AND no lifecycle methods.
//
// Solution: Wrap Expansion constructor to set exposed=true
// BEFORE maplebirch.register(), so v4's ModuleSystem exposes it.

(function() {
  'use strict';

  // Only apply patch if use() doesn't exist (v4.x detection)
  if (typeof maplebirch.use !== 'function') {
    // Wrap Expansion to inject exposed flag
    var OrigExpansion = window.Expansion;
    if (OrigExpansion && !window.__expansionPatched) {
      window.__expansionPatched = true;
      window.Expansion = function() {
        var instance = new OrigExpansion(maplebirch);
        instance.exposed = true;
        return instance;
      };
      window.Expansion.prototype = OrigExpansion.prototype;
    }
  }
})();
