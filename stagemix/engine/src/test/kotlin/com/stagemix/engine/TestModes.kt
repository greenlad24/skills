package com.stagemix.engine

/**
 * The mode these tests specify.
 *
 * KEEP is what the app ships in — it defends the balance already on the
 * desk — and it is the default on [EngineSettings] for that reason. But
 * LEAD is still a real, shipping path: it is what runs when there is no
 * human mix to preserve (a cold start) and after the operator asks for
 * a REBALANCE. Everything the pyramid, the anchor, the groups and the
 * vocal duck do lives there, so the suite that specifies them asks for
 * LEAD explicitly rather than relying on a default that no longer means
 * what it used to.
 */
val LEAD = EngineSettings(mode = BalanceMode.LEAD)

/** LEAD, with the rest of a scenario's settings kept */
fun EngineSettings.lead() = copy(mode = BalanceMode.LEAD)
