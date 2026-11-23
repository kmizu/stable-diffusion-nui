package sdfx.plugins

import sdfx.core.model.GenerationParams
import sdfx.core.plugins.api.*
import sdfx.core.plugins.api.Control.*

object FastModePlugin:
  val Id = "fast_mode"
  val InfotextKey = "Fast mode"

/** One switch for the two training-free speed-ups that were measured on the scala-torch engine (docs/v0.24-verification.md):
  * DeepCache (the deep U-Net features are reused between steps) and guidance for the first part of the steps only (after that the
  * negative prompt is not computed). Built into NUI, not an A1111 extension port.
  *
  * It only fills in what the user has not set: a DeepCache or CFG Schedule plugin that is switched on keeps its own values.
  */
class FastModePlugin extends Plugin:
  import FastModePlugin.*
  def id = Id
  def name = "Fast mode"
  def kind: PluginKind = PluginKind.AlwaysOn
  override def requiresEngineFeatures: Seq[String] = Seq("deepcache", "tgate", "cfg_schedule")
  override def description =
    "Faster sampling combining training-free approximations: DeepCache + TaylorSeer forecasting, T-GATE cross-attention caching, " +
    "and CFG only for the first part of the steps. DeepCache, T-GATE and CFG Schedule keep their own values when switched on."

  override def controls: Seq[Control] = Seq(
    Check("enabled", "Enabled"),
    Slider("guidance_until", "CFG until (fraction of the steps; 1 = all steps)", 0.3, 1, 0.05, 0.7),
    IntField("interval", "DeepCache: full step every N steps (0 = no DeepCache)", 0, 10, 3),
    IntField("order", "TaylorSeer forecast order (0 = reuse, 1 = linear, 2 = quadratic)", 0, 2, 1),
    IntField("gate_step", "T-GATE: cache cross-attention after step (0 = off)", 0, 50, 8))

  override def process(p: GenerationParams, v: Values): GenerationParams =
    val until = math.max(0.0, math.min(1.0, v.double("guidance_until", 0.7)))
    val interval = v.int("interval", 3)
    val order = math.max(0, math.min(2, v.int("order", 1)))
    val gateStep = math.max(0, math.min(50, v.int("gate_step", 8)))
    val withCache =
      if interval < 2 || p.hooks.contains(DeepCachePlugin.Id) then p
      else
        val dc = ujson.Obj("interval" -> interval, "branch" -> 0, "full_first" -> 5)
        if order > 0 then dc("order") = order
        Hooks(p, DeepCachePlugin.Id, dc)._1
    val withTGate =
      if gateStep < 1 || withCache.hooks.contains(TGatePlugin.Id) then withCache
      else Hooks(withCache, TGatePlugin.Id, ujson.Obj("gate_step" -> gateStep))._1
    // The engine skips the negative pass exactly when the scheduled CFG is 1, so the schedule steps from the request's CFG to 1.
    val withGuidance =
      if until >= 1.0 || p.cfgScale <= 1.0 || withTGate.hooks.contains("cfg_schedule") then withTGate
      else Hooks(withTGate, "cfg_schedule", ujson.Obj("start_cfg" -> p.cfgScale, "end_cfg" -> 1.0, "curve" -> "linear",
        "start" -> math.max(0.0, until - 0.01), "end" -> until))._1
    val info = s"CFG until $until, DeepCache interval $interval" +
      (if interval >= 2 && order > 0 then s", TaylorSeer order $order" else "") +
      (if gateStep >= 1 then s", T-GATE step $gateStep" else "")
    withGuidance.copy(extra = withGuidance.extra + (InfotextKey -> info))
