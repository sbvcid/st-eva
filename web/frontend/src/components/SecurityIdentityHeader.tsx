import React from 'react'
import { Building2, Calendar } from 'lucide-react'
import { useI18n } from '../i18n'

interface SecurityIdentityHeaderProps {
  ticker: string
  companyName: string
  currentPrice: number | null | undefined
  currency: string | null | undefined
  asOf?: string | null
  researchId?: string | null
}

export const SecurityIdentityHeader: React.FC<SecurityIdentityHeaderProps> = ({
  ticker,
  companyName,
  currentPrice,
  currency,
  asOf,
  researchId,
}) => {
  const { t } = useI18n()

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs">
      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3 pb-4 border-b border-slate-100">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-2xl font-bold tracking-tight text-slate-900">
              {ticker}
            </span>
            <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-slate-100 text-slate-600">
              {currency || 'USD'}
            </span>
          </div>
          <div className="text-sm text-slate-600 flex items-center gap-1.5 mt-0.5 font-medium">
            <Building2 className="w-4 h-4 text-slate-400 shrink-0" />
            <span>{companyName || 'Unknown Entity'}</span>
          </div>
          <div className="text-lg font-bold text-slate-900 mt-2">
            <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
              {t.results.marketPrice}
            </div>
            {currentPrice !== null && currentPrice !== undefined
              ? `${currency || '$'} ${currentPrice.toFixed(2)}`
              : '—'}
          </div>
        </div>
        <div className="flex sm:flex-col items-baseline sm:items-end gap-2 text-xs text-slate-500 font-mono">
          {asOf && (
            <span className="flex items-center gap-1">
              <Calendar className="w-3.5 h-3.5" /> As of {asOf}
            </span>
          )}
          {researchId && <span className="text-[11px] text-slate-400">ID: {researchId}</span>}
        </div>
      </div>
    </div>
  )
}
