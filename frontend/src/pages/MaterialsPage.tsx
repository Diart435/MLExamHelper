import { useRef, useState, type ChangeEvent, type DragEvent } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import './MaterialsPage.css';

const MAX_FILE_SIZE = 50 * 1024 * 1024;

const UploadIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path
      d="M12 16V5m0 0L7.5 9.5M12 5l4.5 4.5"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <path
      d="M4 15.5v2A2.5 2.5 0 006.5 20h11a2.5 2.5 0 002.5-2.5v-2"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
    />
  </svg>
);

const formatSize = (bytes: number): string => {
  if (!bytes || bytes < 0) return '—';
  const units = ['Б', 'КБ', 'МБ', 'ГБ'];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const rounded = value >= 10 || unit === 0 ? Math.round(value) : Math.round(value * 10) / 10;
  return `${rounded} ${units[unit]}`;
};

const MaterialsPage = () => {
  const { courseId } = useParams<{ courseId: string }>();
  const navigate = useNavigate();

  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadNotice, setUploadNotice] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const onPickClick = () => {
    fileInputRef.current?.click();
  };

  const addFiles = (files: FileList | File[]) => {
    const incoming = Array.from(files);
    if (!incoming.length) return;

    const accepted: File[] = [];
    const problems: string[] = [];

    incoming.forEach((file) => {
      const extension = file.name.split('.').pop()?.toLowerCase() ?? '';
      if (extension !== 'pdf' && extension !== 'docx') {
        problems.push(`${file.name} — только PDF или DOCX`);
      } else if (file.size === 0) {
        problems.push(`${file.name} — пустой файл`);
      } else if (file.size > MAX_FILE_SIZE) {
        problems.push(`${file.name} — больше 50 МБ`);
      } else {
        accepted.push(file);
      }
    });

    if (accepted.length) {
      setPendingFiles((prev) => [...prev, ...accepted]);
      setUploadNotice(null);
    }
    setUploadError(problems.length ? problems.join('; ') : null);
  };

  const removePendingFile = (index: number) => {
    setPendingFiles((prev) => prev.filter((_, itemIndex) => itemIndex !== index));
  };

  const handleFileInput = (event: ChangeEvent<HTMLInputElement>) => {
    if (event.target.files) addFiles(event.target.files);
    event.target.value = '';
  };

  const handleDragOver = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    if (!dragActive) setDragActive(true);
  };

  const handleDragLeave = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    const nextTarget = event.relatedTarget as Node | null;
    if (nextTarget && event.currentTarget.contains(nextTarget)) return;
    setDragActive(false);
  };

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragActive(false);
    if (event.dataTransfer.files) addFiles(event.dataTransfer.files);
  };

  const handleUpload = () => {
    if (!pendingFiles.length) return;
    setUploadNotice(
      `Подготовлено файлов: ${pendingFiles.length}. Отправка на сервер будет подключена на этапе интеграции с API.`,
    );
    setUploadError(null);
  };

  if (!courseId) {
    return (
      <div className="materials-page">
        <div className="materials-page__pattern" aria-hidden="true" />
        <div className="materials-page__content">
          <div className="materials-state is-error">
            <p>Курс не найден</p>
            <span>Вернитесь к списку курсов и откройте материалы нужного курса.</span>
            <button
              type="button"
              className="materials-state__retry"
              onClick={() => navigate('/courses')}
            >
              Ко всем курсам
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="materials-page">
      <div className="materials-page__pattern" aria-hidden="true" />

      <div className="materials-page__content">
        <section className="materials-block">
          <div className="materials-tab">Загрузка материала</div>

          <div className="materials-panel materials-panel--upload">
            <div
              className={`upload-zone${dragActive ? ' is-dragging' : ''}`}
              onClick={onPickClick}
              onDragEnter={handleDragOver}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                multiple
                className="upload-zone__input"
                onChange={handleFileInput}
                tabIndex={-1}
              />

              <span className="upload-zone__icon">
                <UploadIcon />
              </span>
              <h2 className="upload-zone__title">Загрузите материалы</h2>
              <p className="upload-zone__hint">Перетащите файлы сюда или выберите на устройстве</p>
              <p className="upload-zone__formats">PDF или DOCX · до 50 МБ</p>

              {pendingFiles.length > 0 && (
                <ul className="upload-zone__files" onClick={(event) => event.stopPropagation()}>
                  {pendingFiles.map((file, index) => (
                    <li
                      key={`${file.name}-${file.lastModified}-${index}`}
                      className="upload-zone__file"
                    >
                      <span className="upload-zone__file-name" title={file.name}>
                        {file.name}
                      </span>
                      <span className="upload-zone__file-size">{formatSize(file.size)}</span>
                      <button
                        type="button"
                        className="upload-zone__file-remove"
                        onClick={() => removePendingFile(index)}
                        aria-label={`Убрать ${file.name}`}
                      >
                        ×
                      </button>
                    </li>
                  ))}
                </ul>
              )}

              <div className="upload-zone__actions" onClick={(event) => event.stopPropagation()}>
                <button
                  type="button"
                  className="materials-btn materials-btn--outline"
                  onClick={onPickClick}
                >
                  Выберите файлы
                </button>
                {pendingFiles.length > 0 && (
                  <button
                    type="button"
                    className="materials-btn materials-btn--primary"
                    onClick={handleUpload}
                  >
                    Загрузить{pendingFiles.length > 1 ? ` (${pendingFiles.length})` : ''}
                  </button>
                )}
              </div>
            </div>

            {(uploadError || uploadNotice) && (
              <div
                className={`upload-message${uploadError ? ' is-error' : ' is-success'}`}
                role="status"
              >
                {uploadError ?? uploadNotice}
              </div>
            )}
          </div>
        </section>

        <section className="materials-block">
          <div className="materials-tab">
            Материалы
            <span className="materials-tab__count">0</span>
          </div>
          <div className="materials-panel materials-panel--list">
            <div className="materials-placeholder">Список материалов курса появится здесь.</div>
          </div>
        </section>
      </div>
    </div>
  );
};

export default MaterialsPage;
