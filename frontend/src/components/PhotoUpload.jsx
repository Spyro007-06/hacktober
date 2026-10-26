import { useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Camera, Images, X } from 'lucide-react'
import { MAX_PHOTOS, useComplaint } from '../context/ComplaintContext'
import { useLanguage } from '../context/LanguageContext'
import Button from './ui/Button'
import Banner from './ui/Banner'

export default function PhotoUpload() {
  const { t } = useLanguage()
  const { photos, addPhotos, removePhoto, pending } = useComplaint()
  const [notice, setNotice] = useState(null)
  const cameraRef = useRef(null)
  const galleryRef = useRef(null)
  const remaining = MAX_PHOTOS - photos.length

  // Files stay in memory until Continue; nothing is uploaded here.
  function onFiles(e) {
    const files = [...e.target.files]
    e.target.value = '' // allow picking the same file again
    const images = files.filter((f) => f.type.startsWith('image/'))
    if (images.length < files.length) setNotice(t('photos.invalid'))
    else if (images.length > remaining) setNotice(t('photos.max'))
    else setNotice(null)
    if (images.length) addPhotos(images)
  }

  return (
    <section aria-labelledby="photos-title" className="space-y-4">
      <div>
        <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
          <h2 id="photos-title" className="text-section font-bold">
            {t('photos.title')}
          </h2>
          <span className="text-support text-muted">{t('form.optional')}</span>
        </div>
        <p className="mt-1 text-muted">{t('photos.hint')}</p>
      </div>

      {photos.length > 0 && (
        <ul className="grid grid-cols-3 gap-3">
          <AnimatePresence initial={false}>
            {photos.map((photo, i) => (
              <motion.li
                key={photo.id}
                layout
                initial={{ opacity: 0, scale: 0.92 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.92 }}
                transition={{ duration: 0.2 }}
                className="relative aspect-square overflow-hidden rounded-control border border-line bg-surface shadow-card"
              >
                <img src={photo.url} alt={t('photos.alt', { n: i + 1 })} className="size-full object-cover" />
                <button
                  type="button"
                  onClick={() => removePhoto(photo.id)}
                  disabled={Boolean(pending)}
                  aria-label={t('photos.remove', { n: i + 1 })}
                  className="absolute right-1.5 top-1.5 flex size-11 items-center justify-center rounded-full bg-heading/75 text-white transition-colors hover:bg-heading disabled:opacity-50"
                >
                  <X className="size-5" aria-hidden="true" />
                </button>
              </motion.li>
            ))}
          </AnimatePresence>
        </ul>
      )}

      <div className="flex flex-wrap gap-3">
        <Button variant="secondary" icon={Camera} disabled={remaining === 0 || Boolean(pending)} onClick={() => cameraRef.current.click()}>
          {t('photos.take')}
        </Button>
        <Button variant="secondary" icon={Images} disabled={remaining === 0 || Boolean(pending)} onClick={() => galleryRef.current.click()}>
          {t('photos.gallery')}
        </Button>
        <input ref={cameraRef} type="file" accept="image/*" capture="environment" hidden onChange={onFiles} />
        <input ref={galleryRef} type="file" accept="image/*" multiple hidden onChange={onFiles} />
      </div>

      <p className="text-support text-muted" aria-live="polite">
        {remaining > 0 ? t('photos.remaining', { n: remaining }) : t('photos.max')}
      </p>
      {notice && (
        <Banner tone="warning" compact>
          {notice}
        </Banner>
      )}
    </section>
  )
}
