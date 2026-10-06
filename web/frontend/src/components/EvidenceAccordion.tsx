import React, { useState } from 'react'
import { ChevronDown, ChevronRight, Database, ShieldCheck } from 'lucide-react'
import { useI18n } from '../i18n'

interface EvidenceAccordionProps {
  rawAnalysis?: Record<string, any> | null
  sourceIdentifiers?: string[]
}

export const EvidenceAccordion: React.FC<EvidenceAccordionProps> = ({
  rawAnalysis,
  sourceIdentifiers,
}) => {
  const { t } = useI18n()
  const [isOpen, setIsOpen] = useState(false)

  const evidenceIds = rawAnalysis?.evidence_ids || []
  const marketSnapshot = rawAnalysis?.market_snapshot || {}
  const dataQuality = rawAnalysis?.data_quality || {}

  return (
    <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-xs mt-4">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full px-5 py-4 flex items-center justify-between text-left hover:bg-slate-50/50 transition-colors cursor-pointer"
        aria-expanded={isOpen}
      >
        <div className="flex items-center gap-2">
          <Database className="w-4 h-4 text-slate-500" />
          <span className="text-sm font-semibold text-slate-800">
            {t.evidence.title}
          </span>
          <span className="text-xs text-slate-400 font-mono">
            {t.evidence.identifiersCount(evidenceIds.length)}
          </span>
        </div>

        <div className="flex items-center gap-1.5 text-xs font-medium text-slate-500">
          <span>{isOpen ? t.evidence.hideDetails : t.evidence.showDetails}</span>
          {isOpen ? (
            <ChevronDown className="w-4 h-4 text-slate-400" />
          ) : (
            <ChevronRight className="w-4 h-4 text-slate-400" />
          )}
        </div>
      </button>

      {isOpen && (
        <div className="px-5 pb-5 pt-1 border-t border-slate-100 space-y-4 text-xs">
          {/* Source and Provider Metadata */}
          <div>
            <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1.5">
              {t.evidence.sourceAttributions}
            </div>
            <div className="flex flex-wrap gap-2">
              {(sourceIdentifiers || []).map((src, i) => (
                <span
                  key={i}
                  className="px-2.5 py-1 bg-slate-100 rounded-md text-slate-700 font-mono text-[11px]"
                >
                  {src}
                </span>
              ))}
              {marketSnapshot.source && (
                <span className="px-2.5 py-1 bg-slate-100 rounded-md text-slate-700 font-mono text-[11px]">
                  {marketSnapshot.source}
                </span>
              )}
            </div>
          </div>

          {/* Evidence IDs Inventory */}
          <div>
            <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1.5">
              {t.evidence.evidenceContractIds}
            </div>
            {evidenceIds.length > 0 ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 max-h-48 overflow-y-auto pr-1">
                {evidenceIds.map((id: string, i: number) => (
                  <div
                    key={i}
                    className="p-2 bg-slate-50 rounded border border-slate-100 font-mono text-[11px] text-slate-700 flex items-center justify-between"
                  >
                    <span>{id}</span>
                    <ShieldCheck className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-slate-400 italic">{t.evidence.noEvidence}</p>
            )}
          </div>

          {/* Quality Flags */}
          {dataQuality.discrepancy_status && (
            <div className="pt-2 border-t border-slate-100 flex items-center justify-between">
              <span className="text-slate-500">{t.evidence.discrepancyStatus}</span>
              <span className="font-mono font-medium text-slate-700">
                {dataQuality.discrepancy_status}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
