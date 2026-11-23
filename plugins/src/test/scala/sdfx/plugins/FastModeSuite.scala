package sdfx.plugins

import sdfx.core.model.GenerationParams
import sdfx.core.plugins.api.Values

class FastModeSuite extends munit.FunSuite:
  private val plugin = new FastModePlugin
  private def enabled(extra: (String, String)*) =
    Values(Values.defaults(plugin.controls).map ++ Map("enabled" -> "true") ++ extra)

  test("off by default, registered once after DeepCache, T-GATE and CFG Schedule, needs all three engine features"):
    assert(!plugin.isActive(Values.defaults(plugin.controls)))
    assertEquals(plugin.requiresEngineFeatures, Seq("deepcache", "tgate", "cfg_schedule"))
    val ids = StandardPlugins.alwaysOn.map(_.id)
    assertEquals(ids.count(_ == plugin.id), 1)
    assert(ids.indexOf(plugin.id) > ids.indexOf("deepcache") && ids.indexOf(plugin.id) > ids.indexOf("tgate") &&
      ids.indexOf(plugin.id) > ids.indexOf("cfg_schedule"))

  test("defaults: DeepCache interval 3 with order 1, T-GATE step 8, and CFG stepping to 1 at 70 % of the steps"):
    val params = plugin.process(GenerationParams(cfgScale = 6.5), enabled())
    assertEquals(params.hooks("deepcache")("interval").num, 3.0)
    assertEquals(params.hooks("deepcache")("branch").num, 0.0)
    assertEquals(params.hooks("deepcache")("full_first").num, 5.0)
    assertEquals(params.hooks("deepcache")("order").num, 1.0)
    assertEquals(params.hooks("tgate")("gate_step").num, 8.0)
    val schedule = params.hooks("cfg_schedule")
    assertEquals(schedule("start_cfg").num, 6.5)
    assertEquals(schedule("end_cfg").num, 1.0)
    assertEqualsDouble(schedule("start").num, 0.69, 1e-9)
    assertEqualsDouble(schedule("end").num, 0.7, 1e-9)
    assertEquals(params.extra(FastModePlugin.InfotextKey), "CFG until 0.7, DeepCache interval 3, TaylorSeer order 1, T-GATE step 8")

  test("hooks that are already set keep their values"):
    val own = GenerationParams(hooks = Map("deepcache" -> ujson.Obj("interval" -> 5, "branch" -> 1, "full_first" -> 2),
      "tgate" -> ujson.Obj("gate_step" -> 12),
      "cfg_schedule" -> ujson.Obj("start_cfg" -> 9.0, "end_cfg" -> 3.0, "curve" -> "cosine", "start" -> 0.0, "end" -> 1.0)))
    val params = plugin.process(own, enabled())
    assertEquals(params.hooks("deepcache")("interval").num, 5.0)
    assertEquals(params.hooks("tgate")("gate_step").num, 12.0)
    assertEquals(params.hooks("cfg_schedule")("end_cfg").num, 3.0)

  test("each part can be left out: no DeepCache below interval 2, no order at 0, no T-GATE at 0, no schedule at 1 or CFG 1"):
    val noCache = plugin.process(GenerationParams(), enabled("interval" -> "0", "gate_step" -> "0"))
    assert(!noCache.hooks.contains("deepcache") && !noCache.hooks.contains("tgate") && noCache.hooks.contains("cfg_schedule"))
    val noOrder = plugin.process(GenerationParams(), enabled("order" -> "0"))
    assert(!noOrder.hooks("deepcache").obj.contains("order") && noOrder.hooks.contains("tgate"))
    val allSteps = plugin.process(GenerationParams(), enabled("guidance_until" -> "1"))
    assert(allSteps.hooks.contains("deepcache") && allSteps.hooks.contains("tgate") && !allSteps.hooks.contains("cfg_schedule"))
    val noGuidance = plugin.process(GenerationParams(cfgScale = 1.0), enabled())
    assert(!noGuidance.hooks.contains("cfg_schedule"))

  test("FastModePlugin.replay parses v0.31 and v0.28 infotext and rejects malformed values"):
    assertEquals(FastModePlugin.replay(Map.empty), Some(Values(Map("enabled" -> "false"))))
    val p = plugin.process(GenerationParams(cfgScale = 7.0), enabled())
    val restored = FastModePlugin.replay(Map(FastModePlugin.InfotextKey -> p.extra(FastModePlugin.InfotextKey)))
    assertEquals(restored, Some(Values(Map(
      "enabled" -> "true", "guidance_until" -> "0.7", "interval" -> "3", "order" -> "1", "gate_step" -> "8"))))
    // v0.28 format (without TaylorSeer / T-GATE) defaults order and gate_step to 0
    val legacy = FastModePlugin.replay(Map(FastModePlugin.InfotextKey -> "CFG until 0.65, DeepCache interval 4"))
    assertEquals(legacy, Some(Values(Map(
      "enabled" -> "true", "guidance_until" -> "0.65", "interval" -> "4", "order" -> "0", "gate_step" -> "0"))))
    assertEquals(FastModePlugin.replay(Map(FastModePlugin.InfotextKey -> "CFG until 0.1, DeepCache interval 3")), None)
    assertEquals(FastModePlugin.replay(Map(FastModePlugin.InfotextKey -> "CFG until 0.7, Unknown 1")), None)
    assertEquals(FastModePlugin.replay(Map(FastModePlugin.InfotextKey -> "")), None)
