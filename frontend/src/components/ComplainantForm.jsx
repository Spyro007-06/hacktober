import { useLanguage } from '../context/LanguageContext'
import { Input, Textarea } from './ui/Field'

/** Name and address required, phone optional. errors: { name?, address? } as i18n keys. */
export default function ComplainantForm({ value, onChange, errors = {}, disabled }) {
  const { t } = useLanguage()
  return (
    <div className="space-y-5">
      <Input
        label={t('form.name')}
        required
        autoComplete="name"
        value={value.name}
        onChange={(e) => onChange({ name: e.target.value })}
        error={errors.name && t(errors.name)}
        disabled={disabled}
        data-field="name"
      />
      <Textarea
        label={t('form.address')}
        required
        rows={3}
        autoComplete="street-address"
        value={value.address}
        onChange={(e) => onChange({ address: e.target.value })}
        error={errors.address && t(errors.address)}
        disabled={disabled}
        data-field="address"
      />
      <Input
        label={t('form.phone')}
        hint={t('form.phoneHint')}
        type="tel"
        inputMode="tel"
        autoComplete="tel"
        value={value.phone}
        onChange={(e) => onChange({ phone: e.target.value })}
        disabled={disabled}
      />
    </div>
  )
}

export function validateComplainant(c) {
  const errors = {}
  if (!c.name.trim()) errors.name = 'form.nameMissing'
  if (!c.address.trim()) errors.address = 'form.addressMissing'
  return errors
}
