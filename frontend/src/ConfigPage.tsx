import type { AppSettings } from './settings';

type ConfigPageProps = {
  settings: AppSettings;
  onChange: (settings: AppSettings) => void;
};

export function ConfigPage({ settings, onChange }: ConfigPageProps) {
  function update<Key extends keyof AppSettings>(key: Key, value: AppSettings[Key]) {
    onChange({ ...settings, [key]: value });
  }

  return (
    <section className="config-page" aria-labelledby="config-title">
      <div className="config-heading">
        <h1 id="config-title">設定</h1>
        <p>このブラウザだけに保存されます。別の端末やブラウザとは共有されません。</p>
      </div>

      <div className="config-options">
        <label className="config-option">
          <span>
            <strong>ページ切り替え時に先頭へ移動</strong>
            <small>前の日・次の日、月、検索結果、ページ番号を切り替えた時に画面上部へ戻ります。</small>
          </span>
          <input
            type="checkbox"
            checked={settings.scrollToTopOnNavigation}
            onChange={(event) => update('scrollToTopOnNavigation', event.target.checked)}
          />
        </label>

        <label className="config-option">
          <span>
            <strong>レコードIDを表示</strong>
            <small>ポストとリポストにAT Protocolレコードの末尾IDを表示します。</small>
          </span>
          <input
            type="checkbox"
            checked={settings.showRecordIds}
            onChange={(event) => update('showRecordIds', event.target.checked)}
          />
        </label>

        <label className="config-option">
          <span>
            <strong>名前とIDからプロフィールを開く</strong>
            <small>アイコンに加えて、表示名と@handleまたは@DIDもBlueskyプロフィールへのリンクにします。</small>
          </span>
          <input
            type="checkbox"
            checked={settings.linkActorNames}
            onChange={(event) => update('linkActorNames', event.target.checked)}
          />
        </label>

        <label className="config-option">
          <span>
            <strong>削除済みを表示</strong>
            <small>削除済みとして保存されているポストとリポストも一覧へ含めます。</small>
          </span>
          <input
            type="checkbox"
            checked={settings.showDeleted}
            onChange={(event) => update('showDeleted', event.target.checked)}
          />
        </label>

        <label className="config-option">
          <span>
            <strong>Recentを表示</strong>
            <small>右ペインに最近の日付一覧を表示します。</small>
          </span>
          <input
            type="checkbox"
            checked={settings.showRecent}
            onChange={(event) => update('showRecent', event.target.checked)}
          />
        </label>

        <label className="config-option">
          <span>
            <strong>Archivesを表示</strong>
            <small>右ペインに月別アーカイブ一覧を表示します。</small>
          </span>
          <input
            type="checkbox"
            checked={settings.showArchives}
            onChange={(event) => update('showArchives', event.target.checked)}
          />
        </label>

        <label className="config-option">
          <span>
            <strong>Friendsを表示</strong>
            <small>右ペインに返信先一覧を表示します。</small>
          </span>
          <input
            type="checkbox"
            checked={settings.showFriends}
            onChange={(event) => update('showFriends', event.target.checked)}
          />
        </label>

        <label className="config-option">
          <span>
            <strong>自分をFriendsに表示</strong>
            <small>自分の投稿へ返信して続けたポストもFriendsへ含めます。</small>
          </span>
          <input
            type="checkbox"
            checked={settings.showSelfInFriends}
            disabled={!settings.showFriends}
            onChange={(event) => update('showSelfInFriends', event.target.checked)}
          />
        </label>

        <label className="config-option">
          <span>
            <strong>Hashtagsを表示</strong>
            <small>右ペインにハッシュタグ一覧を表示します。</small>
          </span>
          <input
            type="checkbox"
            checked={settings.showHashtags}
            onChange={(event) => update('showHashtags', event.target.checked)}
          />
        </label>

        <label className="config-option">
          <span>
            <strong>センシティブなメディアをぼかす</strong>
            <small>センシティブ指定された投稿の画像と動画をぼかします。投稿ごとに解除できます。</small>
          </span>
          <input
            type="checkbox"
            checked={settings.blurSensitiveMedia}
            onChange={(event) => update('blurSensitiveMedia', event.target.checked)}
          />
        </label>
      </div>
    </section>
  );
}
