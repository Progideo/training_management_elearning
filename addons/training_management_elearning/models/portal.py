from odoo import api, models


class LearningService(models.AbstractModel):
    _inherit = 'training.learning.service'

    @api.private
    def _rows(self,enrollment):
        rows=super()._rows(enrollment)
        usages=self.env['training.elearning.usage'].sudo().search([('delivery_id','=',enrollment.delivery_id.id)])
        by_activity={usage.activity_id.id:usage for usage in usages}
        participant=self._is_participant(enrollment)
        for row in rows:
            usage=by_activity.get(row['id'])
            row['interactive_url']=('/training/interactive/%s/%s' % (enrollment.id,usage.id)
                if usage and participant and row['available'] and usage.version_id.state=='published' else False)
            row['interactive_withdrawn']=bool(usage and usage.version_id.state=='withdrawn')
        return rows
