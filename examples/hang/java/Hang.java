public class Hang {
    public static void main(String[] args) throws InterruptedException {
        System.out.println("Simulating a long running loop...");
        while (true) {
            Thread.sleep(1000);
        }
    }
}
