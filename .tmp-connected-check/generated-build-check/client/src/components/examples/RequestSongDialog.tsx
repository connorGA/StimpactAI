import RequestSongDialog from '../RequestSongDialog';

export default function RequestSongDialogExample() {
  return (
    <RequestSongDialog
      onSubmit={(title, description) => {
        console.log('Request submitted:', { title, description });
      }}
    />
  );
}
