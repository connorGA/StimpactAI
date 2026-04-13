import AdminUploadForm from '../AdminUploadForm';

export default function AdminUploadFormExample() {
  return (
    <div className="max-w-6xl mx-auto">
      <AdminUploadForm
        onSubmit={(data) => {
          console.log('Song uploaded:', data);
        }}
      />
    </div>
  );
}
