public class Crash {
    public static void main(String[] args) {
        System.out.println("About to trigger a NullPointerException");
        String value = null;
        // This will throw a NullPointerException that we can debug with jdb.
        System.out.println(value.length());
    }
}
