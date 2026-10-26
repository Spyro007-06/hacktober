import { useState } from 'react'
import { Pencil, Save } from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'
import { validateComplainant } from './ComplainantForm'
import { Input, Textarea } from './ui/Field'
import Button from './ui/Button'
import LoadingState from './ui/LoadingState'

const TEXT_FIELDS = ['summary_en', 'summary_ta', 'location_text', 'duration']
const PERSON_FIELDS = ['name', 'address', 'phone']
const toLines = (text) => text.split('\n').map((s) => s.trim()).filter(Boolean)

function formFrom(draft, complainant) {
  const f = draft.editable_fields ?? {}
  return {
    ...Object.fromEntries(TEXT_FIELDS.map((k) => [k, f[k] ?? ''])),
    requested_info: (f.requested_info ?? []).join('\n'),
    ...Object.fromEntries(PERSON_FIELDS.map((k) => [k, complainant[k] ?? ''])),
  }
}

/** Only fields that differ from what the backend last returned. */
function diff(form, draft, complainant, editPerson) {
  const orig = draft.editable_fields ?? {}
  const fields = {}
  for (const k of TEXT_FIELDS) if (form[k] !== (orig[k] ?? '')) fields[k] = form[k]
  const info = toLines(form.requested_info)
  if (info.join('\n') !== (orig.requested_info ?? []).join('\n')) fields.requested_info = info
  const person = {}
  if (editPerson) for (const k of PERSON_FIELDS) if (form[k].trim() !== (complainant[k] ?? '')) person[k] = form[k].trim()
  return { fields, complainant: Object.keys(person).length ? person : undefined }
}

/**
 * The backend's official document in a fully sandboxed iframe (no scripts, no same-origin),
 * plus Edit mode for the permitted fields only. Legal wording stays with the backend template.
 * editPerson: false for drafts opened outside the wizard (escalation), where complainant details aren't known here.
 */
export default function DraftPreview({ draft, complainant, onSave, saving, error, editPerson = true }) {
  const { t } = useLanguage()
  const [form, setForm] = useState(null)
  const [errors, setErrors] = useState({})
  const editing = form !== null
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  async function save(e) {
    e.preventDefault()
    const found = editPerson ? validateComplainant(form) : {}
    setErrors(found)
    if (Object.keys(found).length) return
    const changes = diff(form, draft, complainant, editPerson)
    if (!Object.keys(changes.fields).length && !changes.complainant) return setForm(null)
    if (await onSave(changes)) setForm(null)
  }

  return (
    <section aria-labelledby="doc-title" className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <h2 id="doc-title" className="text-xl font-bold">
          {t('draft.document')}
        </h2>
        {!editing && (
          <Button variant="secondary" icon={Pencil} onClick={() => setForm(formFrom(draft, complainant))}>
            {t('btn.edit')}
          </Button>
        )}
      </div>

      <div className="rounded-card border border-line bg-line/50 p-2 sm:p-4">
        <iframe
          title={t('draft.previewTitle')}
          sandbox=""
          srcDoc={draft.html}
          className="block h-[70vh] max-h-[56rem] min-h-[26rem] w-full rounded-[10px] border border-line bg-white shadow-lift"
        />
      </div>

      {editing && (
        <form onSubmit={save} className="space-y-5 rounded-card border border-line bg-surface p-5 shadow-card sm:p-6" noValidate>
          <div>
            <h3 className="text-lg font-bold">{t('draft.editTitle')}</h3>
            <p className="mt-1 text-sm text-muted">{t('draft.legalNote')}</p>
          </div>
          <Textarea label={t('field.summary_ta')} lang="ta" rows={4} value={form.summary_ta} onChange={set('summary_ta')} disabled={saving} />
          <Textarea label={t('field.summary_en')} lang="en" rows={4} value={form.summary_en} onChange={set('summary_en')} disabled={saving} />
          <Input label={t('field.location_text')} value={form.location_text} onChange={set('location_text')} disabled={saving} />
          <Input label={t('field.duration')} value={form.duration} onChange={set('duration')} disabled={saving} />
          <Textarea
            label={t('field.requested_info')}
            hint={t('field.requested_infoHint')}
            rows={3}
            value={form.requested_info}
            onChange={set('requested_info')}
            disabled={saving}
          />
          {editPerson && (
            <div className="space-y-5 border-t border-line pt-5">
              <Input label={t('form.name')} required value={form.name} onChange={set('name')} error={errors.name && t(errors.name)} disabled={saving} />
              <Textarea label={t('form.address')} required rows={3} value={form.address} onChange={set('address')} error={errors.address && t(errors.address)} disabled={saving} />
              <Input label={t('form.phone')} type="tel" inputMode="tel" value={form.phone} onChange={set('phone')} disabled={saving} />
            </div>
          )}
          {error}
          {saving && <LoadingState label={t('loading.saving')} />}
          <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
            <Button variant="ghost" onClick={() => setForm(null)} disabled={saving}>
              {t('btn.cancel')}
            </Button>
            <Button type="submit" icon={Save} loading={saving}>
              {t('btn.save')}
            </Button>
          </div>
        </form>
      )}
    </section>
  )
}
