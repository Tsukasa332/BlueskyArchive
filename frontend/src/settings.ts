export type AppSettings = {
  scrollToTopOnNavigation: boolean;
  showRecordIds: boolean;
  linkActorNames: boolean;
  showDeleted: boolean;
  showRecent: boolean;
  showArchives: boolean;
  showFriends: boolean;
  showHashtags: boolean;
  showSelfInFriends: boolean;
  blurSensitiveMedia: boolean;
};

const STORAGE_KEY = 'bluesky-archive.settings.v1';

export const DEFAULT_SETTINGS: AppSettings = {
  scrollToTopOnNavigation: true,
  showRecordIds: false,
  linkActorNames: false,
  showDeleted: false,
  showRecent: true,
  showArchives: true,
  showFriends: true,
  showHashtags: true,
  showSelfInFriends: false,
  blurSensitiveMedia: false,
};

function booleanSetting(value: boolean | undefined, fallback: boolean) {
  return typeof value === 'boolean' ? value : fallback;
}

export function loadSettings(): AppSettings {
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (!saved) return DEFAULT_SETTINGS;
    const value = JSON.parse(saved) as Partial<AppSettings>;
    return {
      scrollToTopOnNavigation: booleanSetting(value.scrollToTopOnNavigation, DEFAULT_SETTINGS.scrollToTopOnNavigation),
      showRecordIds: booleanSetting(value.showRecordIds, DEFAULT_SETTINGS.showRecordIds),
      linkActorNames: booleanSetting(value.linkActorNames, DEFAULT_SETTINGS.linkActorNames),
      showDeleted: booleanSetting(value.showDeleted, DEFAULT_SETTINGS.showDeleted),
      showRecent: booleanSetting(value.showRecent, DEFAULT_SETTINGS.showRecent),
      showArchives: booleanSetting(value.showArchives, DEFAULT_SETTINGS.showArchives),
      showFriends: booleanSetting(value.showFriends, DEFAULT_SETTINGS.showFriends),
      showHashtags: booleanSetting(value.showHashtags, DEFAULT_SETTINGS.showHashtags),
      showSelfInFriends: booleanSetting(value.showSelfInFriends, DEFAULT_SETTINGS.showSelfInFriends),
      blurSensitiveMedia: booleanSetting(value.blurSensitiveMedia, DEFAULT_SETTINGS.blurSensitiveMedia),
    };
  } catch {
    return DEFAULT_SETTINGS;
  }
}

export function saveSettings(settings: AppSettings) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  } catch {
    // The current state still applies when storage is unavailable.
  }
}
