import { Interaction } from '@web/public/interaction';
import { registry } from '@web/core/registry';

class EnrichedQuestion extends Interaction {
    static selector='.tm_question:has(.tm_enriched)';
    dynamicContent={'.tm_enriched_select':{'t-on-change':this.onSelect},'.tm_clear':{'t-on-click':this.onClear}};
    start() {
        // Keep inputs unavailable until their persistence bridge is attached.
        for (const select of this.el.querySelectorAll('.tm_enriched_select')) select.disabled=false;
    }
    onSelect(event) {
        const select=event.target;
        const selected=select.selectedOptions[0]?.dataset.option;
        // A replacement can move an item: clear the previous row explicitly.
        if(selected) for(const other of this.el.querySelectorAll('.tm_enriched_select')) {
            if(other!==select&&other.selectedOptions[0]?.dataset.option===selected) other.value='';
        }
        for(const current of this.el.querySelectorAll('.tm_enriched_select')) {
            for(const checkbox of this.el.querySelectorAll('.tm_enriched_value')) {
                if(checkbox.dataset.row===current.dataset.row) checkbox.checked=checkbox.value===current.value;
            }
        }
        this.el.querySelector('.tm_enriched_value').dispatchEvent(new Event('change',{bubbles:true}));
    }
    onClear() {
        for(const select of this.el.querySelectorAll('.tm_enriched_select')) select.value='';
        // Native TrainingExam clears checkboxes and persists the empty answer.
    }
}
registry.category('public.interactions').add('training_management_elearning.enriched',EnrichedQuestion);
