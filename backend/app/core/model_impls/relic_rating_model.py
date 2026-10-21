from app.core.review import evaluate
from app.core.interfaces.model_interface import ModelInterface
from app.core.network_models.responses.relic_analysis_response import RelicScoreResponse

class RelicRatingModel(ModelInterface):
    @staticmethod
    def get_name():
        return "relic_rating_model"

    def __init__(self, global_state_manager):
        self.global_state_manager = global_state_manager

    def load(self):
        pass

    def predict(self, input_data):
        relic = input_data.model_dump()
        title = (relic.get('relic_title') or {}).get('title')
        rules = self.global_state_manager.get_state().get('formatted_rules', {}).get(title, [])
        result = evaluate(relic, [r.model_dump() for r in rules])
        return [RelicScoreResponse(**s) for s in result['scores']]
