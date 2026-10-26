import { motion } from 'framer-motion'
import { Input } from './ui/Field'

/** One input per backend question, labelled in the UI language; answers are written in the complaint language. */
export default function FollowUpQuestions({ questions, uiLang, complaintLang, answers, onChange, disabled }) {
  return (
    <ul className="space-y-5">
      {questions.map((q, i) => (
        <motion.li
          key={q.field}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.22, delay: i * 0.05 }}
          className="rounded-card border border-line bg-surface p-4 shadow-card sm:p-5"
        >
          <Input
            label={uiLang === 'ta' ? q.question_ta : q.question_en}
            lang={complaintLang}
            value={answers[q.field] ?? ''}
            onChange={(e) => onChange(q.field, e.target.value)}
            disabled={disabled}
          />
        </motion.li>
      ))}
    </ul>
  )
}
