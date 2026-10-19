"""Dagster view of the same steps: one asset per step, wired in order, plus a small job for a quick check."""
from dagster import AssetExecutionContext, AssetSelection, Definitions, asset, define_asset_job

from filepipe import pipeline as p


def _meta(ctx: AssetExecutionContext, out: dict) -> dict:
    ctx.add_output_metadata({"result": str(out)[:2000]})
    return out


@asset(group_name="intake")
def packets(context: AssetExecutionContext) -> dict:
    return _meta(context, p.step_packets(300))


@asset(group_name="intake", deps=[packets])
def ocr_text(context: AssetExecutionContext) -> dict:
    return _meta(context, p.step_ocr())


@asset(group_name="intake", deps=[ocr_text])
def extraction_eval(context: AssetExecutionContext) -> dict:
    return _meta(context, p.step_extract())


@asset(group_name="intake", deps=[extraction_eval])
def extraction_gate(context: AssetExecutionContext) -> dict:
    return _meta(context, p.step_gates())


@asset(group_name="intake", deps=[extraction_gate])
def azure_side_by_side(context: AssetExecutionContext) -> dict:
    return _meta(context, p.step_azure())


@asset(group_name="intake", deps=[extraction_eval])
def dataverse_export(context: AssetExecutionContext) -> dict:
    return _meta(context, p.step_export())


@asset(group_name="intake", deps=[extraction_eval])
def trustee_notes(context: AssetExecutionContext) -> dict:
    return _meta(context, p.step_notes())


@asset(group_name="proposals")
def survival_radar(context: AssetExecutionContext) -> dict:
    return _meta(context, p.step_radar())


@asset(group_name="growth")
def lead_to_file(context: AssetExecutionContext) -> dict:
    return _meta(context, p.step_leads())


@asset(group_name="growth")
def osb_demand(context: AssetExecutionContext) -> dict:
    return _meta(context, p.step_demand())


@asset(group_name="warehouse", deps=[extraction_gate, azure_side_by_side, dataverse_export, trustee_notes, survival_radar, lead_to_file, osb_demand])
def warehouse(context: AssetExecutionContext) -> dict:
    out = p.step_warehouse()
    p.scoreboard()
    return _meta(context, out)


file_to_finish = define_asset_job("file_to_finish", selection=AssetSelection.all())
growth_only = define_asset_job("growth_only", selection=AssetSelection.groups("growth"))

defs = Definitions(assets=[packets, ocr_text, extraction_eval, extraction_gate, azure_side_by_side, dataverse_export, trustee_notes, survival_radar,
                           lead_to_file, osb_demand, warehouse], jobs=[file_to_finish, growth_only])
