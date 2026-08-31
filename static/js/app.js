document.addEventListener("DOMContentLoaded", () => {
    window.setTimeout(() => {
        document.querySelectorAll(".alert-dismissible").forEach((element) => {
            if (window.bootstrap) bootstrap.Alert.getOrCreateInstance(element).close();
        });
    }, 5000);
});
