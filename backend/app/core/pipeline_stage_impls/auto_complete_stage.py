from app.core.pipeline_stage_impls.single_complete_stage import SingleCompleteStage

class AutoCompleteStage(SingleCompleteStage):
    @staticmethod
    def get_name():
        return "auto_complete_stage"
