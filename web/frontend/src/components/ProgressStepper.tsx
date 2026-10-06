import React from 'react'
import { JobProgressStage } from '../types/api'
import { CheckCircle2, Circle, Loader2 } from 'lucide-react'
import { useI18n } from '../i18n'

interface ProgressStepperProps {
  currentStage: JobProgressStage
}

export const ProgressStepper: React.FC<ProgressStepperProps> = ({ currentStage }) => {
  const { t } = useI18n()

  const stages: { stage: JobProgressStage; label: string }[] = [
    { stage: 'resolving', label: t.stepper.resolving },
    { stage: 'fetching SEC', label: t.stepper.fetchingSec },
    { stage: 'admission', label: t.stepper.admission },
    { stage: 'valuation', label: t.stepper.valuation },
    { stage: 'archive/replay', label: t.stepper.archiveReplay },
  ]

  const getStageIndex = (stage: JobProgressStage): number => {
    switch (stage) {
      case 'pending':
        return 0
      case 'resolving':
        return 0
      case 'fetching SEC':
        return 1
      case 'admission':
        return 2
      case 'valuation':
        return 3
      case 'archive/replay':
        return 4
      case 'completed':
        return 5
      case 'failed':
        return -1
      default:
        return 0
    }
  }

  const currentIndex = getStageIndex(currentStage)

  return (
    <div className="w-full bg-white rounded-xl border border-slate-200 p-5 shadow-xs mb-6">
      <div className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-4 flex items-center justify-between">
        <span>{t.stepper.progressTitle}</span>
        {currentStage !== 'completed' && currentStage !== 'failed' && (
          <span className="flex items-center gap-1.5 text-blue-600 font-mono text-[11px] lowercase">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            {currentStage}
          </span>
        )}
      </div>

      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-2">
        {stages.map((step, idx) => {
          const isDone = currentIndex > idx
          const isCurrent = currentIndex === idx

          return (
            <div
              key={step.stage}
              className={`flex items-center gap-2.5 sm:flex-1 ${
                idx < stages.length - 1
                  ? "sm:after:content-[''] sm:after:h-[2px] sm:after:flex-1 sm:after:mx-2 sm:after:bg-slate-100"
                  : ''
              } ${isDone ? 'sm:after:bg-emerald-200' : ''}`}
            >
              <div className="shrink-0">
                {isDone ? (
                  <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                ) : isCurrent ? (
                  <Loader2 className="w-5 h-5 text-blue-600 animate-spin" />
                ) : (
                  <Circle className="w-5 h-5 text-slate-300" />
                )}
              </div>
              <span
                className={`text-xs font-medium ${
                  isDone
                    ? 'text-slate-800'
                    : isCurrent
                    ? 'text-blue-700 font-semibold'
                    : 'text-slate-400'
                }`}
              >
                {step.label}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
