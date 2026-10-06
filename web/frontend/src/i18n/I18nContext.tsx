import React, { createContext, useContext, useState, useEffect } from 'react'
import { Language, Translations } from './types'
import { en } from './en'
import { zhTW } from './zhTW'

export const STORAGE_KEY = 'st_eva_lang'

export function detectBrowserLanguage(): Language {
  if (typeof window === 'undefined' || typeof navigator === 'undefined') {
    return 'en'
  }
  const browserLangs =
    navigator.languages && navigator.languages.length > 0
      ? navigator.languages
      : [navigator.language || 'en']

  for (const raw of browserLangs) {
    if (!raw) continue
    const l = raw.toLowerCase()
    if (
      l.startsWith('zh-tw') ||
      l.startsWith('zh-hk') ||
      l.startsWith('zh-mo') ||
      l.startsWith('zh-hant') ||
      l === 'zh'
    ) {
      return 'zh-TW'
    }
  }
  return 'en'
}

export function getInitialLanguage(): Language {
  if (typeof window !== 'undefined') {
    try {
      const stored = localStorage.getItem(STORAGE_KEY)
      if (stored === 'zh-TW' || stored === 'en') {
        return stored
      }
    } catch {
      // Ignore storage access errors
    }
  }
  return detectBrowserLanguage()
}

interface I18nContextValue {
  language: Language
  setLanguage: (lang: Language) => void
  toggleLanguage: () => void
  t: Translations
}

const I18nContext = createContext<I18nContextValue | null>(null)

export const I18nProvider: React.FC<{
  initialLang?: Language
  children: React.ReactNode
}> = ({ initialLang, children }) => {
  const [language, setLanguageState] = useState<Language>(
    initialLang || getInitialLanguage()
  )

  const setLanguage = (newLang: Language) => {
    setLanguageState(newLang)
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(STORAGE_KEY, newLang)
      } catch {
        // Ignore storage write errors
      }
    }
  }

  const toggleLanguage = () => {
    setLanguage(language === 'zh-TW' ? 'en' : 'zh-TW')
  }

  const t = language === 'zh-TW' ? zhTW : en

  return (
    <I18nContext.Provider value={{ language, setLanguage, toggleLanguage, t }}>
      {children}
    </I18nContext.Provider>
  )
}

export function useI18n(): I18nContextValue {
  const context = useContext(I18nContext)
  if (!context) {
    return {
      language: 'en',
      setLanguage: () => {},
      toggleLanguage: () => {},
      t: en,
    }
  }
  return context
}
